"""Recover the nine exact Care Compare distribution URLs from the qualified artifact.
Print only aggregate release metadata; never print or publish source rows or database.
"""
import argparse
import json
from pathlib import Path
from build_combined import validate_base,require
from restore_snapshot import load_lock
import collect_cms

def supplement(lock_path,base,out):
    lock=load_lock(lock_path);manifest=validate_base(base)
    require(manifest["db_sha256"]==lock["care_compare_baseline"]["sha256"],"unexpected retained baseline")
    sources={s["dataset"]:s for s in manifest["sources"]}
    for item in lock["sources"]:
        if item["family"]!="care-compare":continue
        s=sources[item["key"]];meta=s["metadata"]
        require(meta["id"]==item["catalog_id"] and meta["released"]==item["release"] and s["sha256"]==item["sha256"] and s["bytes"]==item["bytes"] and s["expected_rows"]==item["input_rows"],"Care Compare pin discrepancy")
        item["download_url"]=collect_cms.allowed(meta["url"])
        item["metadata"]=meta
    lock["limitations"]=[x for x in lock["limitations"] if not x.startswith("Care Compare direct distribution URLs")]
    lock["limitations"].append("Care Compare distribution URLs recovered from retained verified manifest; availability of exact historical files not guaranteed.")
    require(not out.exists(),"supplement output exists")
    out.write_text(json.dumps(lock,indent=2)+"\n",encoding="utf-8")
    print("CARE_COMPARE_RELEASE_URLS",json.dumps([{k:s[k] for k in ("key","download_url","sha256","release")} for s in lock["sources"] if s["family"]=="care-compare"]),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--lock",type=Path,required=True);p.add_argument("--base",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();supplement(a.lock,a.base,a.output)
