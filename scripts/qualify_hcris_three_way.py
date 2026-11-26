"""Three-way historical provider and fiscal-period corroboration, aggregate only.

Use publisher S-2 worksheet coordinates as a third observation; do not choose
a date locale merely because two raw strings match. Exact source pins required.
No Azure access, no publication, no row-level output or currency scaling.
"""
import argparse,csv,hashlib,io,json,re,tempfile,zipfile
from collections import Counter,defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from build_combined import require
from scripts import archive_hcris_form_indexes as forms
from scripts import qualify_hcris_measure_crosswalk as measures
from scripts import qualify_hcris_provider_period as previous
ROOT=Path(__file__).resolve().parents[1]
# Pinned publisher dictionaries: worksheet S2 Part I.
FIELDS={
 "hospital":{"ccn":("S200001","00300","00200"),"state":("S200001","00200","00200"),"begin":("S200001","02000","00100"),"end":("S200001","02000","00200")},
 "snf":{"ccn":("S200001","00400","00200"),"state":("S200001","00200","00200"),"begin":("S200001","01400","00100"),"end":("S200001","01400","00200")}}
DOCS={
 "hospital":"https://www.cms.gov/Regulations-and-Guidance/Guidance/Transmittals/Downloads/R7P240s.pdf",
 "snf":"https://www.cms.gov/Regulations-and-Guidance/Guidance/Transmittals/downloads/R2P241.pdf"}
# CMS form instructions specify month/day/year; exported ISO also accepted.
# No day/month fallback, year truncation or fuzzy comparison.
def documented_date(raw):
    s=raw.strip()
    if not s:return None,"blank"
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",s):
        try:return date.fromisoformat(s),"iso"
        except ValueError:return None,"invalid_iso"
    m=re.fullmatch(r"([0-9]{1,2})/([0-9]{1,2})/([0-9]{4})",s)
    if not m:return None,"unsupported_shape"
    a,b,y=map(int,m.groups())
    try:v=date(y,a,b)
    except ValueError:return None,"invalid_mdy"
    return v,"mdy_ambiguous_without_documentation" if 1<=a<=12 and 1<=b<=12 and a!=b else "mdy_unambiguous"
def alpha_fields(path,form,headers):
    wanted={v:k for k,v in FIELDS[form].items()}
    observed=defaultdict(lambda:defaultdict(list));rows=0;unknown=0
    with zipfile.ZipFile(path) as z:
        annual=any(re.fullmatch(r"[A-Za-z0-9]+_2024_(alpha|nmrc|rpt)\.csv",Path(i.filename).name,re.I) for i in z.infolist())
        if annual:
            groups=forms.annual_groups(z);require(set(groups)=={"2024"},"annual ZIP scope");roles=groups["2024"]
        else:roles=forms.members(z)
        with z.open(roles["alpha"]) as raw,io.TextIOWrapper(raw,encoding="latin-1",newline="") as f:
            for rows,r in enumerate(csv.reader(f,strict=True),1):
                require(rows<=forms.MAX_ROWS and len(r)==5,"alpha member row shape/bound")
                name=wanted.get(tuple(v.strip() for v in r[1:4]))
                if name:
                    if r[0].strip() not in headers:unknown+=1;continue
                    observed[r[0].strip()][name].append(r[4].strip())
    return observed,{"screened_alpha_rows":rows,"target_rows_with_unresolved_parent":unknown}
def exact_alpha(fields,name):
    vals=fields.get(name,[])
    if not vals:return None,"absent"
    if len(vals)!=1:return None,"duplicate"
    return vals[0],"single"
def assess(headers,puf,alpha,directory):
    statuses=Counter();alpha_states=Counter();date_shapes=Counter();comparison=Counter();periods=defaultdict(list)
    for key in set(headers)&set(puf):
        hc,hb,he=headers[key];pc,st,pb,pe=puf[key]
        fields=alpha.get(key,{})
        av={}
        for name in ("ccn","state","begin","end"):
            av[name],state=exact_alpha(fields,name);alpha_states[name+"_"+state]+=1
        parsed=[]
        for label,raw in (("rpt_begin",hb),("rpt_end",he),("puf_begin",pb),("puf_end",pe),("alpha_begin",av["begin"] or ""),("alpha_end",av["end"] or "")):
            day,shape=documented_date(raw);date_shapes[label+"_"+shape]+=1;parsed.append(day)
        hstart,hend,pstart,pend,astart,aend=parsed
        if hstart and pstart:comparison["rpt_puf_begin_equal" if hstart==pstart else "rpt_puf_begin_conflict"]+=1
        if hend and pend:comparison["rpt_puf_end_equal" if hend==pend else "rpt_puf_end_conflict"]+=1
        d=directory.get(pc,{})
        if any(len(fields.get(n,[]))!=1 for n in ("ccn","state","begin","end")):status="alpha_missing_or_duplicate"
        elif hc!=pc or av["ccn"]!=pc or av["state"]!=st:status="identity_conflict"
        elif None in parsed:status="unresolved_date_shape"
        elif not(hstart==pstart==astart and hend==pend==aend):status="date_conflict"
        elif pend<pstart:status="reversed_period"
        elif not date(2023,10,1)<=pstart<=date(2024,9,30):status="outside_fy2024_begin_scope"
        elif d.get(st,0)!=1 or sum(d.values())!=1:status="directory_not_unique_exact"
        else:
            status="three_way_candidate";periods[(pc,st)].append((pstart,pend))
        statuses[status]+=1
    duplicates=overlaps=conflicted=0
    for rows in periods.values():
        touched=set()
        for i,(a,b) in enumerate(rows):
            for j,(c,d) in enumerate(rows[:i]):
                if (a,b)==(c,d):duplicates+=1
                elif a<=d and c<=b:overlaps+=1
                else:continue
                touched.update((i,j))
        conflicted+=len(touched)
    n=len(set(headers)&set(puf));eligible=statuses["three_way_candidate"]
    require(sum(statuses.values())==n and sum(alpha_states.values())==4*n and sum(date_shapes.values())==6*n,"cohort accounting")
    return {"report_key_intersection":n,"candidate_states":dict(statuses),"alpha_field_states":dict(alpha_states),"date_shapes":dict(date_shapes),"rpt_puf_documented_date_comparison":dict(comparison),"candidate_provider_records":len(periods),"duplicate_period_pairs":duplicates,"overlap_period_pairs":overlaps,"candidate_reports_in_period_conflicts":conflicted,"nonconflicting_three_way_candidate_reports":eligible-conflicted}
def unit_shapes(records,form):
    out={}
    for name,coord in measures.MAPS[form].items():
        kind=coord[3];counts=Counter()
        for r in records.values():
            val,state=r[name]
            if val is None:counts["missing"]+=1
            elif val!=val.to_integral_value():counts["fractional"]+=1
            elif val<0:counts["negative_integer"]+=1
            elif val==0:counts["zero"]+=1
            else:counts["positive_integer"]+=1
        require(sum(counts.values())==len(records),"measure shape accounting")
        out[name]={"unit_candidate":kind,"coordinate":list(coord[:3]),"shape_counts":dict(counts),"monetary_scaling_qualified":False}
    return out
def run(form,root):
    cov=json.loads((root/"research/coverage_status.json").read_text());audit=cov[form+"_cost_qualified_baseline"]["audit"]
    crosswalk=json.loads((root/"research/hcris_direct_measure_crosswalk_20261126.json").read_text())["forms"][form]
    old=json.loads((root/"research/hcris_provider_period_candidates_20261126.json").read_text())["forms"][form]
    require(audit["source_sha256"]==crosswalk["puf_sha256"]==old["puf_sha256"],"PUF receipt pins")
    raw=measures.download(audit["publisher"]["url"],"text/csv",audit["bytes"])
    puf=previous.parse_puf_identity(raw,audit,form)
    units=unit_shapes(measures.parse_puf(raw,audit,measures.MAPS[form]),form)
    with tempfile.TemporaryDirectory(prefix="hcris-three-way-") as temp:
        path=Path(temp)/"source.zip";meta=forms.discover(form);receipt=forms.download(meta,path)
        require(receipt["sha256"]==crosswalk["archive_source_sha256"]==old["archive_sha256"] and forms.discover(form)==meta,"archive source pin")
        headers,_,_=previous.report_headers(path)
        alpha,shape=alpha_fields(path,form,headers)
    directory,dmeta=previous.directory_index(root,form);require(dmeta==old["directory"],"directory source pin")
    result=assess(headers,puf,alpha,directory)
    require(result["report_key_intersection"]==old["report_key_intersection"]==crosswalk["report_key_intersection"],"prior overlap cohort pin")
    return {"status":"COMPLETE_CANDIDATE_AUDIT","form":form,"publisher_archive_sha256":receipt["sha256"],"puf_sha256":audit["source_sha256"],"directory":dmeta,"form_date_spec":DOCS[form],"worksheet_dictionary":crosswalk["dictionary_url"],"alpha_coordinates":FIELDS[form],**shape,**result,"measure_numeric_shape_audit":units,"monetary_scale_qualified":False,"publication_cleared":False,"facility_financial_attribution":False,"individual_values_retained":False,"azure_writes":0}
def main():
    p=argparse.ArgumentParser();p.add_argument("--form",choices=FIELDS,required=True);p.add_argument("--receipt",type=Path,required=True);a=p.parse_args()
    require(not a.receipt.exists(),"receipt exists")
    result=run(a.form,ROOT)
    with a.receipt.open("x") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print("HCRIS_THREE_WAY_CANDIDATE_AUDIT",json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":main()
