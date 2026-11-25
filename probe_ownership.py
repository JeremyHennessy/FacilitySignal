"""Qualify ownership catalog releases and sample schemas; never retain row data."""
import json
from datetime import datetime,timezone
from pathlib import Path
from collect_registry import CATALOG,get_json,allowed,expected_rows

TARGETS={
 "hospital-enrollment":"Hospital Enrollments",
 "hospital-owner":"Hospital All Owners",
 "hospital-chow":"Hospital Change of Ownership",
 "hospital-additional-npis":"Hospital Additional NPIs",
 "hospital-additional-addresses":"Hospital Additional Addresses",
 "snf-enrollment":"Skilled Nursing Facility Enrollments",
 "snf-owner":"Skilled Nursing Facility All Owners",
 "snf-chow":"Skilled Nursing Facility Change of Ownership",
 "hha-owner":"Home Health Agency All Owners",
 "hospice-owner":"Hospice All Owners",
}
POS_TITLES=("Provider of Services File - Quality Improvement and Evaluation System","Provider of Services File - Internet Quality Improvement and Evaluation System","Provider of Services File - Clinical Laboratories")

def select(catalog,title):
    matches=[d for d in catalog["dataset"] if d.get("title")==title]
    if len(matches)!=1: raise ValueError("missing or ambiguous exact catalog title")
    d=matches[0]
    if d.get("accessLevel")!="public": raise ValueError("not public")
    dist=d.get("distribution",[])
    latest=[x for x in dist if x.get("format")=="API" and x.get("description")=="latest"]
    if len(latest)!=1 or not latest[0].get("temporal"): raise ValueError("ambiguous latest API")
    period=latest[0]["temporal"]
    versions=[x["accessURL"] for x in dist if x.get("format")=="API" and x.get("description")!="latest" and x.get("temporal")==period and x.get("accessURL")]
    if len(versions)!=1: raise ValueError("ambiguous version")
    files=[x for x in dist if x.get("temporal")==period and x.get("downloadURL") and (x.get("format","").upper() in ("CSV","ZIP") or x.get("mediaType") in ("text/csv","application/zip"))]
    return {"title":title,"period":period,"modified":d.get("modified"),"license":d.get("license"),"api":allowed(versions[0]),"distributions":[{"url":allowed(x["downloadURL"]),"format":x.get("format"),"media_type":x.get("mediaType")} for x in files],"landing":d.get("landingPage")}

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    catalog=get_json(CATALOG)
    results={}
    for key,title in TARGETS.items():
        try:
            r=select(catalog,title)
            r["expected_rows"]=expected_rows(r)
            # One public API sample; emit keys only, never owner names or addresses.
            sample=get_json(r["api"]+"?size=1")
            if not isinstance(sample,list) or len(sample)!=1 or not isinstance(sample[0],dict):
                raise ValueError("unexpected sample response")
            r["columns"]=list(sample[0])
            r["status"]="access_schema_sample_verified"
            r["note"]="Sample header and version count only; no full download or import; ownership roles are self-reported, not deed ownership."
            results[key]=r
        except Exception as e:
            results[key]={"title":title,"status":"blocked_or_unverified","reason":type(e).__name__+": "+str(e)[:150]}
        print("OWNERSHIP_PROBE",key,json.dumps(results[key]),flush=True)
    docs={}
    for title in POS_TITLES:
        entries=[d for d in catalog["dataset"] if d.get("title")==title]
        if len(entries)==1:
            d=entries[0]
            docs[title]={"landing":d.get("landingPage"),"references":d.get("references"),"documentation": [{"title":x.get("title"),"description":x.get("description"),"url":x.get("downloadURL") or x.get("accessURL"),"format":x.get("format")} for x in d.get("distribution",[]) if x.get("format","").upper() in ("PDF","XLSX","XLS","HTML") and "API"!=x.get("format")]}
    audit={"retrieved_at":datetime.now(timezone.utc).isoformat(),"source":CATALOG,"results":results,"pos_documentation":docs,"note":"No full rows retained. Each source requires complete file reconciliation, field semantics, and privacy/reuse review."}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(audit,indent=2)+"\n")
    if not any(v["status"]=="access_schema_sample_verified" for v in results.values()): raise SystemExit("No ownership sample qualified")

if __name__=="__main__":main()
