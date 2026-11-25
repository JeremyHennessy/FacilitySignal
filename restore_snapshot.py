"""Recover the exact qualified source release set into a new local snapshot.

Never overwrite an existing database; do not upload raw data or row-level artifacts.
Local archives are preferred; fetching missing files requires explicit --download.
A changed or unavailable source fails closed. New import timestamps mean the rebuilt
SQLite bytes need not equal the historical database hash.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
import facilitysignal as fs
import collect_cms as cms
import collect_registry as registry
import collect_qcor_hospital as qcor
import collect_ownership as ownership
from build_combined import require,check_integrity,sha

ROOT=Path(__file__).resolve().parent
LOCK=ROOT/"research"/"snapshot_release_20261125.json"
FAMILIES={"care-compare":set(fs.CATALOG),"registry":set(registry.TITLES),"qcor":{"qcor-hospital"},"pecos":set(ownership.PINS)}

def load_lock(path):
    obj=json.loads(path.read_text(encoding="utf-8"))
    items=obj["sources"]
    require(obj["format_version"]==1 and len(items)==19,"lock format/source count")
    require({(s["family"],s["key"]) for s in items}=={(f,k) for f,keys in FAMILIES.items() for k in keys},"source coverage mismatch")
    require(len({s["file"] for s in items})==len(items),"duplicate raw filename")
    for s in items:
        require(s["file"] in (s["key"]+".csv",s["key"]+".xlsx",s["key"]+".zip"),"unexpected raw filename")
        require(type(s["bytes"]) is int and s["bytes"]>0 and len(s["sha256"])==64 and all(c in "0123456789abcdef" for c in s["sha256"]),"invalid source checksum/size")
        require(s["input_rows"]==s["stored_rows"]+s["excluded_rows"],"input row reconciliation")
        if s["family"]=="care-compare":
            require(s["catalog_id"]==fs.CATALOG[s["key"]][0],"catalog identity mismatch")
            if s["download_url"]: cms.allowed(s["download_url"])
        elif s["family"] in ("registry","pecos"):
            require(s["download_url"]==s["metadata"]["url"],"download URL discrepancy")
            registry.allowed(s["download_url"])
        else:
            require(s["download_url"]==qcor.URL,"QCOR URL mismatch")
    require(sum(s["stored_rows"] for s in items)==obj["source_records_total"],"total mismatch")
    return obj

def verify_raw(path,item):
    require(path.is_file() and not path.is_symlink(),"raw source missing or symlink: "+item["key"])
    require(path.stat().st_size==item["bytes"],"source size changed: "+item["key"])
    require(sha(path)==item["sha256"],"source checksum changed: "+item["key"])

def fetch_missing(item,dest):
    family=item["family"];key=item["key"]
    if family=="care-compare":
        url=item["download_url"]
        require(bool(url),"pinned Care Compare download URL required: "+key)
        with cms.response(url) as src,dest.open("xb") as out:
            n=0
            while chunk:=src.read(1024*1024):
                n+=len(chunk)
                require(n<=item["bytes"],"source exceeded pinned size: "+key)
                out.write(chunk)
    elif family in ("registry","pecos"):
        registry.download(item["metadata"],dest)
    else:
        from scripts.probe_qcor_hospital import download
        download(dest)
    verify_raw(dest,item)

def materialize(item,raw_dir,stage,allow_download):
    path=raw_dir/item["file"] if raw_dir else None
    if path and (path.exists() or path.is_symlink()):
        verify_raw(path,item)
        return path
    require(allow_download,"source absent; explicit --download required: "+item["key"])
    dest=stage/item["file"]
    fetch_missing(item,dest)
    return dest

def import_one(db_path,item,path):
    verify_raw(path,item)
    key=item["key"];n=item["input_rows"];digest=item["sha256"];family=item["family"]
    if family=="care-compare":
        result=fs.import_csv(db_path,key,path,item["release"],n)
        require(result["stored_rows"]==item["stored_rows"] and result["duplicate_rows"]==item["excluded_rows"] and result["sha256"]==digest,"Care Compare import mismatch: "+key)
    elif family=="registry":
        result=registry.import_registry(db_path,item["metadata"],path,digest,n)
        require(result["rows"]==item["stored_rows"],"registry import mismatch: "+key)
    elif family=="qcor":
        meta={"sha256":digest,"bytes":item["bytes"],"retrieved_at":item["retrieved_at"]}
        result=qcor.import_workbook(db_path,path,meta,n)
        require(result["stored_rows"]==item["stored_rows"] and result["rejected_rows"]==0,"QCOR import mismatch")
    else:
        with closing(sqlite3.connect(db_path)) as db:
            ownership.init(db)
            result=ownership.ingest(db,key,item["metadata"],path,digest,n)
        require(result["stored_rows"]==item["stored_rows"] and result["excluded_individual_rows"]==item["excluded_rows"],"ownership import mismatch: "+key)
    verify_raw(path,item)

def audit_db(path,lock):
    expected={s["key"]:s for s in lock["sources"]}
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        check_integrity(db)
        actual={}
        for key,digest,n,stored,excluded in db.execute("SELECT dataset,sha256,input_rows,stored_rows,duplicate_rows FROM releases"):
            actual[key]=(digest,n,stored,excluded)
        for key,digest,n in db.execute("SELECT registry,source_sha256,row_count FROM certification_releases"):
            actual[key]=(digest,n,n,0)
        for digest,n,stored in db.execute("SELECT source_sha256,expected_rows,stored_rows FROM qcor_hospital_releases"):
            require("qcor-hospital" not in actual,"unexpected QCOR history")
            actual["qcor-hospital"]=(digest,n,stored,0)
        for key,digest,n,stored,excluded in db.execute("SELECT source,sha256,expected_rows,stored_rows,excluded_individual_rows FROM pecos_releases"):
            actual[key]=(digest,n,stored,excluded)
        require(actual=={k:(s["sha256"],s["input_rows"],s["stored_rows"],s["excluded_rows"]) for k,s in expected.items()},"release lock mismatch")
        counts={}
        for table in ("facilities","findings","certification_records","qcor_hospital_rows","pecos_enrollment_rows","pecos_org_role_rows","pecos_chow_rows"):
            counts[table]=db.execute("SELECT count(*) FROM "+table).fetchone()[0]
        require(sum(counts.values())==lock["source_records_total"],"total row reconciliation")
        for table,field in (("facilities","dataset"),("findings","dataset"),("certification_records","registry"),("pecos_enrollment_rows","source"),("pecos_org_role_rows","source"),("pecos_chow_rows","source")):
            for key,n in db.execute("SELECT "+field+",count(*) FROM "+table+" GROUP BY "+field):
                require(n==expected[key]["stored_rows"],"per-source row count mismatch: "+key)
        require(counts["qcor_hospital_rows"]==expected["qcor-hospital"]["stored_rows"],"QCOR row count mismatch")
        require(db.execute("SELECT count(*) FROM current_release").fetchone()[0]==9 and db.execute("SELECT count(*) FROM qcor_hospital_current").fetchone()[0]==1,"current release coverage")
        links=ownership.audit_linkage(db)
        require(all(v["unmatched_org_role_rows"]==0 for v in links.values()),"ownership linkage regression")
    return counts

def recover(lock_path,raw_dir,output,allow_download,with_capabilities=False):
    lock=load_lock(lock_path)
    output=output.resolve()
    require(not output.exists(),"output must be new")
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".snapshot-recovery-",dir=output.parent) as tmp:
        stage=Path(tmp);raw=stage/"raw";raw.mkdir();ready=stage/"ready";ready.mkdir()
        db=ready/"facilitysignal.sqlite3"
        fs.init(db)
        projections={}
        if with_capabilities:
            from recovery_capabilities import prepare_dictionaries,project_one,audit_projections
            dictionaries=prepare_dictionaries(raw_dir,raw,allow_download)
        for s in sorted(lock["sources"],key=lambda x:({"care-compare":0,"registry":1,"qcor":2,"pecos":3}[x["family"]],x["key"])):
            path=materialize(s,raw_dir,raw,allow_download)
            import_one(db,s,path)
            if with_capabilities and s["family"]=="registry" and s["key"] in ("iqies","qies"):
                projections[s["key"]]=project_one(db,s,path,dictionaries)
            if path.parent==raw: path.unlink()
            print("RECOVERED_SOURCE",s["key"],s["stored_rows"],flush=True)
        counts=audit_db(db,lock)
        manifest={"source_lock_sha256":sha(lock_path),"source_records_total":sum(counts.values()),"table_counts":counts,"database_sha256":sha(db),"database_bytes":db.stat().st_size,"reconstructed_at":datetime.now(timezone.utc).isoformat(),"note":"Logical source reconstruction, not a byte-for-byte restoration; no production or reuse clearance."}
        if with_capabilities:
            manifest["capabilities"]=audit_projections(db,projections)
        (ready/"recovery-audit.json").write_text(json.dumps(manifest,indent=2)+"\n")
        os.rename(ready,output)
        print("RECOVERY_VERIFIED",json.dumps(manifest),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lock",type=Path,default=LOCK);p.add_argument("--raw-dir",type=Path);p.add_argument("--output",type=Path,required=True);p.add_argument("--download",action="store_true")
    p.add_argument("--with-capabilities",action="store_true",help="Also recover the separately qualified iQIES and QIES projections using the pinned dictionaries")
    a=p.parse_args();recover(a.lock,a.raw_dir.resolve() if a.raw_dir else None,a.output,a.download,a.with_capabilities)
if __name__=="__main__":main()
