"""Narrow follow-up on two non-identifying, bounded hospital classification columns."""
import argparse,csv,json,re,tempfile
from collections import Counter
from pathlib import Path
from restore_snapshot import materialize,verify_raw
from pos_raw_field_profile import read,need,LOCK
from care_compare_provider_semantics import ROOT,HEADERS,PROFILES,ENUMS
FIELDS={"Hospital Type":(9,36),"Hospital Ownership":(12,43)}
def distributions(rows):
    counts={f:Counter() for f in FIELDS};n=0
    for r in rows:
        n+=1
        for f,(cap,length) in FIELDS.items():
            v=r[f].strip()
            need(0<len(v)<=length and re.fullmatch(r"[A-Za-z][A-Za-z /()'&.,-]*",v),"unexpected category token")
            counts[f][v]+=1
            need(len(counts[f])<=cap,"category cardinality exceeds prior raw profile")
    for f,(cap,length) in FIELDS.items():need(len(counts[f])==cap and sum(counts[f].values())==n,"classification count mismatch")
    return {f:dict(c) for f,c in counts.items()}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path);a=p.parse_args();need(not a.output.exists(),"new output required")
    pin=next(s for s in read(LOCK)["sources"] if s["key"]=="hospital")
    h=next(s for s in read(HEADERS)["sources"] if s["source"]=="hospital")
    prior=next(s for s in read(PROFILES)["sources"] if s["source"]=="hospital")
    need(h["source_sha256"]==prior["source_sha256"]==pin["sha256"],"source lineage")
    for f,(cap,length) in FIELDS.items():
        pf=next(x for x in prior["fields"] if x["field"]==f)
        need(pf["distinct_nonmissing"]=={"count":cap,"method":"exact"} and pf["max_nonmissing_trimmed_length"]==length,"bounded profile mismatch")
    with tempfile.TemporaryDirectory(prefix="hospital-enum-followup-") as d:
        path=materialize(pin,a.raw_dir,Path(d),a.download);verify_raw(path,pin)
        with path.open(encoding="utf-8-sig",newline="") as stream:
            reader=csv.DictReader(stream);need(reader.fieldnames==[f["field"] for f in h["fields"]],"header mismatch")
            counts=distributions(reader)
        verify_raw(path,pin)
    for c in counts.values():need(sum(c.values())==pin["stored_rows"],"source row count")
    observed={f:{v:n for v,n in c.items() if v.casefold() not in {x.casefold() for x in ENUMS[f]}} for f,c in counts.items()}
    result={"format_version":1,"source_sha256":pin["sha256"],"period":pin["release"],"rows":pin["stored_rows"],"classification_counts":counts,"not_in_initial_dictionary_based_list":observed,"scope":"Only literal hospital type and ownership category labels, not legal owners, unique sites or property classification. No individual rows or arbitrary values published."}
    with a.output.open("x",encoding="utf-8") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print("HOSPITAL_ENUM_FOLLOWUP",json.dumps(result,separators=(",",":"),sort_keys=True),flush=True)
if __name__=="__main__":main()
