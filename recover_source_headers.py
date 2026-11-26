"""Recover complete source headers from previously qualified audit manifests; no source redownload."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def require(ok,msg):
    if not ok: raise ValueError(msg)
def read(path): return json.loads(path.read_text(encoding="utf-8"))
def recover(cms,pecos,lock):
    items={s["key"]:s for s in lock["sources"] if s["family"] in ("care-compare","pecos")}
    rows=[]
    for family,manifest in (("care-compare",cms),("pecos",pecos)):
        seen=set()
        for s in manifest["sources"]:
            key=s["dataset"] if family=="care-compare" else s["source"]
            require(key in items and items[key]["family"]==family and key not in seen,"unexpected manifest source")
            seen.add(key)
            pin=items[key]
            require(s["sha256"]==pin["sha256"] and s["bytes"]==pin["bytes"],"pinned source hash/size mismatch: "+key)
            if family=="care-compare":
                require(s["expected_rows"]==pin["input_rows"] and s["metadata"]["released"]==pin["release"],
                        "Care Compare release mismatch")
                require(s["import"]["stored_rows"]==pin["stored_rows"],"Care Compare stored count mismatch")
            else:
                require(s["input_rows"]==pin["input_rows"] and s["stored_rows"]==pin["stored_rows"] and
                        s["excluded_individual_rows"]==pin["excluded_rows"] and s["metadata"]["period"]==pin["release"],
                        "PECOS release/count mismatch")
            header=s["columns"]
            require(isinstance(header,list) and header and all(isinstance(f,str) and f.strip() for f in header)
                    and len(header)==len(set(header)),"invalid or duplicate raw header")
            rows.append({"source":key,"family":family,"source_sha256":pin["sha256"],"period":pin["release"],
                         "input_rows":pin["input_rows"],"stored_rows":pin["stored_rows"],"field_count":len(header),
                         "fields":[{"ordinal":i+1,"field":f,"semantic_status":"exact_header_only"} for i,f in enumerate(header)]})
        require(seen=={k for k,v in items.items() if v["family"]==family},"missing manifest sources")
    require(len(rows)==15,"expected fifteen manifest sources")
    return {"format_version":1,"scope":"Exact pinned release headers recovered from qualified historical audit manifests, not raw value profiles.",
            "sources":rows,"source_count":len(rows),"field_count":sum(r["field_count"] for r in rows)}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("cms","pecos","output"): p.add_argument("--"+key,type=Path,required=True)
    a=p.parse_args()
    result=recover(read(a.cms),read(a.pecos),read(ROOT/"research/snapshot_release_20261125.json"))
    result["evidence"]={"cms_run":45664651617,"cms_artifact":15044944704,
                        "pecos_run":45675883927,"pecos_artifact":15052006792,
                        "cms_manifest_sha256":hashlib.sha256(a.cms.read_bytes()).hexdigest(),
                        "pecos_manifest_sha256":hashlib.sha256(a.pecos.read_bytes()).hexdigest()}
    with a.output.open("x",encoding="utf-8") as f: json.dump(result,f,indent=2); f.write("\n")
    print("RECOVERED_HEADER_SUMMARY",json.dumps({k:v for k,v in result.items() if k!="sources"}),flush=True)
    for s in result["sources"]:
        print("RECOVERED_HEADER_SOURCE",json.dumps(s,separators=(",",":")),flush=True)
if __name__=="__main__": main()
