"""Bounded, read-only candidate qualification of FY2024 report-header identity.

Do not release row-level identifiers or monetary data. Candidate RPT positions
are tested against exact pinned PUF records, never inferred from matching names.
No Azure credentials or writes; both publisher downloads must match prior pins.
"""
import argparse,csv,hashlib,io,json,re,tempfile,zipfile
from collections import Counter,defaultdict
from pathlib import Path
from build_combined import require
from scripts import archive_hcris_form_indexes as forms
from scripts import qualify_hcris_measure_crosswalk as measures
from scripts.qualify_hospital_cost import calendar,norm
ROOT=Path(__file__).resolve().parents[1]
CORE=("rpt_rec_num","Provider CCN","State Code","Fiscal Year Begin Date","Fiscal Year End Date")
# ResDAC's published Hospital Report File ordered field list (RPT, 18 columns).
# SNF is a candidate of the same layout; parity must be measured independently.
LAYOUT=(0,2,5,6)
def parse_puf_identity(data,audit,form):
    verified=measures.parse_puf(data,audit,measures.MAPS[form])
    reader=csv.DictReader(io.StringIO(data.decode("utf-8-sig"),newline=""),strict=True)
    fields={norm(k):k for k in reader.fieldnames or []}
    require(all(norm(k) in fields for k in CORE),"PUF identity schema")
    out={}
    for row in reader:
        key,ccn,state,begin,end=(row[fields[norm(k)]].strip() for k in CORE)
        require(key in verified and key not in out,"PUF report identity uniqueness")
        require(re.fullmatch(r"[A-Z0-9]{6}",ccn) and re.fullmatch(r"[A-Z]{2}",state),"PUF provider shape")
        out[key]=(ccn,state,begin,end)
    require(set(out)==set(verified),"PUF identity/measure key reconciliation")
    return out
def report_headers(path):
    result={};widths=Counter();shapes=Counter()
    with zipfile.ZipFile(path) as z:
        annual=any(re.fullmatch(r"[A-Za-z0-9]+_2024_(alpha|nmrc|rpt)\.csv",Path(i.filename).name,re.I) for i in z.infolist())
        if annual:
            groups=forms.annual_groups(z);require(set(groups)=={"2024"},"annual ZIP scope");roles=groups["2024"]
        else:roles=forms.members(z)
        with z.open(roles["report"]) as raw,io.TextIOWrapper(raw,encoding="latin-1",newline="") as f:
            for ordinal,row in enumerate(csv.reader(f,strict=True),1):
                require(ordinal<=150000 and len(row)==18,"candidate RPT width differs from documented layout")
                key,ccn,begin,end=(row[i].strip() for i in LAYOUT)
                require(re.fullmatch(r"[0-9]{1,20}",key) and key not in result,"RPT exact report key")
                widths[str(len(row))]+=1
                shapes["six_character_provider" if re.fullmatch(r"[A-Z0-9]{6}",ccn) else "provider_shape_review"]+=1
                result[key]=(ccn,begin,end)
    require(result and sum(widths.values())==len(result)==sum(shapes.values()),"RPT accounting")
    return result,dict(widths),dict(shapes)
def date_pair(a,b):
    ad,ast=calendar(a);bd,bst=calendar(b)
    if ad is None or bd is None:
        return "unresolved"
    return "equal" if ad==bd else "conflict"
def directory_index(root,form):
    source="hospital" if form=="hospital" else "nursing"
    manifest=json.loads((root/"web/public-directory/manifest.json").read_text())
    path=root/"web/public-directory"/(source+".json")
    raw=path.read_bytes();d=json.loads(raw)
    require(d["source"]==source and len(d["records"])==d["row_count"]==manifest["sources"][source]["published_records"],"directory manifest scope")
    out=defaultdict(Counter)
    for r in d["records"]:
        ccn,state=r["ccn"],r["state"]
        require(isinstance(ccn,str) and isinstance(state,str),"directory identifier type")
        out[ccn][state]+=1
    return out,{"source":source,"release":d["release"],"sha256":hashlib.sha256(raw).hexdigest(),"rows":d["row_count"]}
def evaluate(headers,puf,directory):
    matched=set(headers)&set(puf);ccn_states=Counter();date_states=Counter();link_states=Counter();period_states=Counter()
    periods=defaultdict(list)
    for key in matched:
        hc,hb,he=headers[key];pc,st,pb,pe=puf[key]
        same=hc==pc
        ccn_states["equal" if same else "conflict"]+=1
        begin,end=date_pair(hb,pb),date_pair(he,pe)
        date_states["begin_"+begin]+=1;date_states["end_"+end]+=1
        d=directory.get(pc,{})
        link="exact_ccn_state_unique" if d.get(st,0)==1 and sum(d.values())==1 else "ambiguous_directory" if d.get(st,0)>0 else "state_conflict" if d else "unmatched_ccn"
        link_states[link]+=1
        a,_=calendar(pb);b,_=calendar(pe)
        if not same:status="ccn_conflict"
        elif begin=="conflict" or end=="conflict":status="fiscal_date_conflict"
        elif begin!="equal" or end!="equal":status="unresolved_fiscal_dates"
        elif b<a:status="reversed_period"
        elif link!="exact_ccn_state_unique":status="provider_link_"+link
        else:status="candidate_exact_report_provider_period";periods[(pc,st)].append((a,b))
        period_states[status]+=1
    require(sum(ccn_states.values())==sum(link_states.values())==sum(period_states.values())==len(matched),"intersection accounting")
    require(sum(date_states.values())==2*len(matched),"date accounting")
    duplicates=0;overlaps=0;multi=0;colliding_reports=0
    for rows in periods.values():
        if len(rows)>1:multi+=1
        touched=set()
        for i,(a,b) in enumerate(rows):
            for j,(c,d) in enumerate(rows[:i]):
                if a==c and b==d:duplicates+=1
                elif a<=d and c<=b:overlaps+=1
                else:continue
                touched.update((i,j))
        colliding_reports+=len(touched)
    candidate=period_states["candidate_exact_report_provider_period"]
    require(sum(map(len,periods.values()))==candidate and colliding_reports<=candidate,"period accounting")
    return {"report_key_intersection":len(matched),"archive_only_report_keys":len(set(headers)-matched),"puf_only_report_keys":len(set(puf)-matched),"ccn_comparisons":dict(ccn_states),"date_comparisons":dict(date_states),"directory_link_states":dict(link_states),"joint_eligibility_states":dict(period_states),"candidate_providers":len(periods),"providers_with_multiple_candidate_reports":multi,"duplicate_period_pairs":duplicates,"overlapping_distinct_period_pairs":overlaps,"candidate_reports_in_period_conflicts":colliding_reports,"nonconflicting_candidate_reports":candidate-colliding_reports}
def run(form,root):
    cov=json.loads((root/"research/coverage_status.json").read_text());audit=cov[form+"_cost_qualified_baseline"]["audit"]
    crosswalk=json.loads((root/"research/hcris_direct_measure_crosswalk_20261126.json").read_text())["forms"][form]
    ledger=json.loads((root/"research/azure_archive_inventory_20261126.json").read_text())
    pins=[x for x in ledger["receipts"] if x["key"]==f"hcris-{form}-2024-index" and x["kind"]=="publisher"]
    require(len(pins)==1,"archive parent pin")
    pin=pins[0];require(pin["source_sha256"]==crosswalk["archive_source_sha256"] and audit["source_sha256"]==crosswalk["puf_sha256"],"crosswalk input pins")
    puf=parse_puf_identity(measures.download(audit["publisher"]["url"],"text/csv",audit["bytes"]),audit,form)
    with tempfile.TemporaryDirectory(prefix="hcris-header-") as d:
        path=Path(d)/"source.zip"
        meta=forms.discover(form);receipt=forms.download(meta,path)
        require(receipt["sha256"]==pin["source_sha256"] and forms.discover(form)==meta,"publisher archive bytes/link drift")
        headers,widths,shapes=report_headers(path)
    require(len(headers)==pin["observations"]==crosswalk["archive_reports"] and len(puf)==crosswalk["puf_reports"],"report count pins")
    directory,source=directory_index(root,form);result=evaluate(headers,puf,directory)
    for key in ("report_key_intersection","archive_only_report_keys","puf_only_report_keys"):
        require(result[key]==crosswalk[key],"crosswalk cohort mismatch")
    return {"status":"COMPLETE_CANDIDATE_AUDIT","form":form,"archive_sha256":pin["source_sha256"],"puf_sha256":audit["source_sha256"],"report_width_counts":widths,"provider_shape_counts":shapes,"directory":source,"candidate_layout":"ResDAC ordered RPT fields, positions 1,3,6,7; SNF candidate independently tested",**result,"monetary_scale_qualified":False,"facility_financial_attribution":False,"individual_values_retained":False,"public_promotion":False,"azure_writes":0}
def main():
    p=argparse.ArgumentParser();p.add_argument("--form",choices=("hospital","snf"),required=True);p.add_argument("--receipt",type=Path,required=True);a=p.parse_args()
    require(not a.receipt.exists(),"receipt exists")
    result=run(a.form,ROOT)
    with a.receipt.open("x") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print("HCRIS_PROVIDER_PERIOD_CANDIDATE_AUDIT",json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":main()
