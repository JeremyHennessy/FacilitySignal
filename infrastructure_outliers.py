"""Outlier diagnostics only; no suppression, repair, or market-total approval."""
import argparse,json,tempfile
from collections import Counter,defaultdict
from decimal import Decimal
from pathlib import Path
from restore_snapshot import materialize
from clia_domain_link_audit import stream,read,need,LOCK,INVENTORY
from qies_infrastructure_audit import ROOT,identity,load_public,number
from iqies_capabilities import load_dictionary,normalize_code,normalize_value
from probe_iqies_dictionary import download as download_dictionary
def rank(xs,p):
    need(bool(xs) and 1<=p<=100,"invalid percentile")
    return xs[(len(xs)*p+99)//100-1]
def summarize(vals,states):
    positives=sorted(x for x in vals if x>0)
    need(len(vals)==states.get("positive",0)+states.get("zero",0),"numeric count mismatch")
    out={"states":states,"positive_count":len(positives)}
    if positives:
        p99=rank(positives,99);total=sum(positives)
        out.update(positive_p50=str(rank(positives,50)),positive_p95=str(rank(positives,95)),positive_p99=str(p99),maximum=str(positives[-1]),positive_above_10x_p99=sum(x>10*p99 for x in positives),maximum_share_of_positive_sum=str((100*positives[-1]/total).quantize(Decimal("0.0001"))))
    return out
def add(stats,values,f,state,x):
    stats[f][state]+=1
    if x is not None:values[f].append(x)
def qies_audit(rows,public,prior):
    old=prior["scope_results"]["code00_same_state_hospital_candidate"]
    fields={**{k:False for k in old["counts"] if "BED_CNT" in k or "ROOM" in k},**dict.fromkeys(old["fte"],True)}
    stats=defaultdict(Counter);values=defaultdict(list);raw=n=0;ratios=defaultdict(list)
    for r in rows:
        raw+=1
        need(r["PRVDR_CTGRY_CD"].strip() in ("01","1"),"hospital scope drift")
        _,_,same=identity(r,public)
        if r["PGM_TRMNTN_CD"].strip()!="00" or not same:continue
        n+=1;_,beds=number(r["BED_CNT"])
        for f,fte in fields.items():
            state,x=number(r[f],fte);add(stats,values,f,state,x)
            if fte and x is not None and beds is not None and beds>0:ratios[f].append(x/beds)
    need(raw==prior["source_rows"] and n==old["rows"],"hospital cohort drift")
    out={}
    for f,fte in fields.items():
        need(sum(stats[f].values())==n,"field count drift")
        ref=(old["fte"] if fte else old["counts"])[f]
        need(dict(stats[f])==ref["states"],"prior value states drift "+f)
        s=summarize(values[f],stats[f])
        if values[f]:need(max(values[f])==Decimal(ref["range"]["max"]),"prior maximum drift "+f)
        if fte and ratios[f]:
            positive=sorted(x for x in ratios[f] if x>0)
            s["fte_to_reported_total_beds_diagnostic"]={"comparable_rows":len(ratios[f]),"positive_ratio_p99":str(rank(positive,99).quantize(Decimal("0.0001"))) if positive else None,"rows_ratio_over_10":sum(x>10 for x in ratios[f])}
        out[f]=s
    return {"source_rows":raw,"cohort_rows":n,"fields":out,"blocked_hospital_operating_room_field":prior["blocked_field"]["reason"]}
def iqies_audit(rows,scopes,prior):
    fields=("oprtg_room_cnt","procedure_room_cnt")
    stats=defaultdict(Counter);values=defaultdict(list);raw=n=0
    for r in rows:
        raw+=1
        if scopes.get(normalize_code(r["prvdr_type_id"]))!="ASC":continue
        n+=1
        for f in fields:
            state,x=normalize_value(r[f],"count")
            add(stats,values,f,("positive" if x else "zero") if x is not None else state,Decimal(x) if x is not None else None)
    need(raw==prior["rows"] and n==prior["provider_scope_counts"]["ASC"],"ASC scope drift")
    for f in fields:need(sum(stats[f].values())==n,"ASC value reconciliation")
    return {"source_rows":raw,"cohort_rows":n,"fields":{f:summarize(values[f],stats[f]) for f in fields}}
def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path);a=p.parse_args()
    pins={s["key"]:s for s in read(LOCK)["sources"]};inv=read(INVENTORY)["registries"]
    qprior=read(ROOT/"research/qies_hospital_infrastructure_audit_20261126.json")
    iprior=read(ROOT/"research/iqies_raw_field_profile_20261126.json")
    public,meta=load_public(ROOT,pins["hospital"])
    need(qprior["source_sha256"]==pins["qies"]["sha256"] and iprior["source_sha256"]==pins["iqies"]["sha256"],"source provenance drift")
    with tempfile.TemporaryDirectory() as d:
        stage=Path(d);q=materialize(pins["qies"],a.raw_dir,stage,a.download)
        qresult=qies_audit(stream(q,pins["qies"],inv["qies"]),public,qprior)
        i=materialize(pins["iqies"],a.raw_dir,stage,a.download)
        dic=stage/"dictionary.xlsx";need(a.download,"dictionary download requires explicit permission");download_dictionary(dic)
        _,_,scopes=load_dictionary(dic)
        iresult=iqies_audit(stream(i,pins["iqies"],inv["iqies"]),scopes,iprior)
    out={"source_hashes":{k:pins[k]["sha256"] for k in ("qies","iqies")},"public_hospital":meta,"qies":qresult,"iqies":iresult,"limits":"Nearest rank percentiles among positive values only. 10x p99 and FTE/bed >10 are exploratory screens, not error or staffing benchmarks. No records discarded or changed; all counts retain their original source scope. No individual identifiers or market sums emitted."}
    with a.output.open("x") as f:json.dump(out,f,indent=2,sort_keys=True)
    print("INFRASTRUCTURE_OUTLIERS",json.dumps(out,sort_keys=True))
if __name__=="__main__":main()
