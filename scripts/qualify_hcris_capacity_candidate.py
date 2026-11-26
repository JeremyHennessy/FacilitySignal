"""Narrow selected-PUF historical capacity projection rehearsal.

Build an allowlisted report-grain candidate in memory, validate its exact
receipt cohort and field domains, and retain ONLY aggregate evidence and SHA.
Do not publish row-level values, read Azure, or qualify monetary measures.
"""
import argparse,hashlib,json,tempfile
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from build_combined import require
from scripts import archive_hcris_form_indexes as forms
from scripts import qualify_hcris_measure_crosswalk as measures
from scripts import qualify_hcris_provider_period as prev
from scripts import qualify_hcris_three_way as three
ROOT=Path(__file__).resolve().parents[1]
FIELDS={"hospital":{"Number of Beds":"available_beds_at_period_end"},"snf":{"Number of Beds":"available_beds_at_period_end","Total Bed Days Available":"available_bed_days"}}
def integer_or_missing(value):
    if value is None:return None
    require(value>=0 and value==value.to_integral_value() and value<=9007199254740991,"unsafe historical capacity value")
    return int(value)
def valid_measure_receipt(receipt,form):
    for name in FIELDS[form]:
        m=receipt["measures"][name]
        require(m["coordinate"]==list(measures.MAPS[form][name][:3]),"measure coordinate pin")
        require(m["qualification"]=="matched_report_parity_supported" and m["archive_duplicate_coordinate_report_keys"]==0,"measure parity/duplicate gate")
        counts=m["comparisons"]
        require(set(counts)<= {"equal_decimal","puf_missing_archive_absent"} and sum(counts.values())==receipt["report_key_intersection"],"measure comparison scope")
def candidate_records(headers,puf,alpha,directory,numeric,form):
    records=[];periods=defaultdict(list)
    for key in sorted(set(headers)&set(puf)):
        hc,hb,he=headers[key];pc,st,pb,pe=puf[key];f=alpha.get(key,{})
        if any(len(f.get(k,[]))!=1 for k in ("ccn","state","begin","end")):continue
        if hc!=pc or f["ccn"][0]!=pc or f["state"][0]!=st:continue
        dt=[three.documented_date(v)[0] for v in (hb,he,pb,pe,f["begin"][0],f["end"][0])]
        if None in dt:continue
        a,b,c,d,e,g=dt
        if not(a==c==e and b==d==g and c<=d and date(2023,10,1)<=c<=date(2024,9,30)):continue
        states=directory.get(pc,{})
        if states.get(st,0)!=1 or sum(states.values())!=1:continue
        vals={label:integer_or_missing(numeric[key][name][0]) for name,label in FIELDS[form].items()}
        record={"report_key":key,"ccn":pc,"state":st,"period_begin":c.isoformat(),"period_end":d.isoformat(),"measures":vals}
        records.append(record);periods[(pc,st)].append((c,d))
    for rows in periods.values():
        for i,(a,b) in enumerate(rows):
            require(all(not(a<=d and c<=b) for c,d in rows[:i]),"candidate period collision; fail closed")
    return records
def summarize(records,form,prior):
    require(len(records)==prior["nonconflicting_three_way_candidate_reports"],"candidate count differs from three-way receipt")
    require(len({r["report_key"] for r in records})==len(records),"duplicate report keys")
    providers=len({(r["ccn"],r["state"]) for r in records})
    require(providers==prior["candidate_provider_records"],"candidate provider count differs")
    counts={label:Counter() for label in FIELDS[form].values()}
    allow={"report_key","ccn","state","period_begin","period_end","measures"}
    for r in records:
        require(set(r)==allow and set(r["measures"])==set(counts),"projection field allowlist")
        for label,v in r["measures"].items():
            require(v is None or type(v) is int and 0<=v<=9007199254740991,"projection numeric shape")
            counts[label]["missing" if v is None else "reported_zero" if v==0 else "reported_positive"]+=1
    pack={"version":1,"scope":"FY2024 selected CMS PUF historical report capacity; exact matched candidate cohort, not current certified capacity","form":form,"records":records}
    raw=(json.dumps(pack,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
    return {"candidate_reports":len(records),"candidate_providers":providers,"field_value_states":{k:dict(v) for k,v in counts.items()},"ephemeral_candidate_bytes":len(raw),"ephemeral_candidate_sha256":hashlib.sha256(raw).hexdigest(),"row_level_output_retained":False,"public_promotion":False,"monetary_values_included":False}
def run(form,root,*,candidate_sink=None):
    cov=json.loads((root/"research/coverage_status.json").read_text())[form+"_cost_qualified_baseline"]["audit"]
    cross=json.loads((root/"research/hcris_direct_measure_crosswalk_20261126.json").read_text())["forms"][form]
    prior=json.loads((root/"research/hcris_three_way_candidates_20261126.json").read_text())["forms"][form]
    require(cov["source_sha256"]==cross["puf_sha256"]==prior["puf_sha256"],"PUF pin")
    require(cov["publisher"]["license"]=="https://www.usa.gov/government-works","publisher license candidate pin")
    valid_measure_receipt(cross,form)
    raw=measures.download(cov["publisher"]["url"],"text/csv",cov["bytes"])
    puf=prev.parse_puf_identity(raw,cov,form)
    numeric=measures.parse_puf(raw,cov,measures.MAPS[form])
    with tempfile.TemporaryDirectory(prefix="hcris-capacity-pilot-") as tmp:
        path=Path(tmp)/"source.zip";meta=forms.discover(form);archive=forms.download(meta,path)
        require(archive["sha256"]==cross["archive_source_sha256"]==prior["publisher_archive_sha256"] and forms.discover(form)==meta,"archive source pin")
        headers,_,_=prev.report_headers(path);alpha,_=three.alpha_fields(path,form,headers)
    directory,dmeta=prev.directory_index(root,form)
    require(dmeta==prior["directory"],"directory pin")
    check=three.assess(headers,puf,alpha,directory)
    for key in ("candidate_states","report_key_intersection","candidate_provider_records","nonconflicting_three_way_candidate_reports","candidate_reports_in_period_conflicts"):
        require(check[key]==prior[key],"three-way receipt mismatch")
    require(check["candidate_reports_in_period_conflicts"]==0,"overlap gate")
    records=candidate_records(headers,puf,alpha,directory,numeric,form)
    receipt={"status":"COMPLETE_CANDIDATE_REHEARSAL","form":form,"source_sha256":cov["source_sha256"],"archive_sha256":archive["sha256"],"directory":dmeta,"publisher_license":cov["publisher"]["license"],"measure_dictionary":cross["dictionary_url"],"fields":FIELDS[form],**summarize(records,form,prior),"azure_writes":0}
    if candidate_sink is not None:candidate_sink(records,receipt)
    return receipt
def main():
    p=argparse.ArgumentParser();p.add_argument("--form",choices=FIELDS,required=True);p.add_argument("--receipt",type=Path,required=True);a=p.parse_args()
    require(not a.receipt.exists(),"receipt exists")
    r=run(a.form,ROOT)
    with a.receipt.open("x") as f:json.dump(r,f,indent=2,sort_keys=True);f.write("\n")
    print("HCRIS_CAPACITY_CANDIDATE_REHEARSAL",json.dumps(r,sort_keys=True),flush=True)
if __name__=="__main__":main()
