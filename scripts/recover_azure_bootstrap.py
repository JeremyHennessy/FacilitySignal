"""Recover the exact failed Azure bootstrap upload without reuploading data.

Use the original successful reconstruction audit and Git tree as independent
expected bytes. Only create the original release's completion receipt and the
absent national pointer after every remote payload and local SQLite check passes.
No source retrieval, data replacement, deletion or public data changes.
"""
import argparse,hashlib,json,os,re,sqlite3,subprocess,tempfile
from contextlib import closing
from pathlib import Path
import azure_national_archive as archive
from build_combined import require,sha,readonly,check_integrity
from restore_snapshot import LOCK,load_lock,audit_db
from private_snapshot_archive import validate
from scripts.azure_inventory import verify_inventory

ROOT=Path(__file__).resolve().parents[1]
PIN=ROOT/"research/azure_bootstrap_recovery_pin_20261126.json"
RELEASE="bootstrap-45845760984-1"
ORIGINAL_COMMIT="25ed486112a82a202b3f379adbbb9613b4e54b8d"
PREFIX=archive.PREFIX+"/releases/"+RELEASE
PAYLOAD=PREFIX+"/files"
COMPLETE=PREFIX+"/complete.json"

class RecoverAzure(archive.Azure):
    def create(self,name,stream,size,kind):
        require(name in {COMPLETE,archive.POINTER},"recovery write restricted to receipt/pointer")
        return super().create(name,stream,size,kind)
    def delete_probe(self,name,etag):
        raise ValueError("recovery never deletes data")

def load_pin():
    p=json.loads(PIN.read_text())
    a=p["reconstruction_audit"]
    require(p["format_version"]==1 and p["run"]==45845760984 and p["attempt"]==1 and p["release"]==RELEASE and p["commit"]==ORIGINAL_COMMIT and p["failure"]=="archive ETags changed","recovery lineage")
    require(a["source_records_total"]==1904060 and a["database_bytes"]==906149888 and a["database_sha256"]=="138ad57c3719fe63895eeaff702c04b51107fe1cf6dc4daf403a554985a1f033" and a["source_lock_sha256"]==sha(LOCK),"reconstruction evidence mismatch")
    return p

def expected_records(pin):
    a=pin["reconstruction_audit"]
    # restore_snapshot.py originally wrote this exact JSON representation.
    audit_bytes=(json.dumps(a,indent=2)+"\n").encode()
    records=[{"path":"snapshot/facilitysignal.sqlite3","bytes":a["database_bytes"],"sha256":a["database_sha256"]},archive.bytes_record("snapshot/recovery-audit.json",audit_bytes)]
    paths=subprocess.check_output(["git","ls-tree","-r","--name-only","-z",pin["commit"],"--","research","web"],cwd=ROOT).decode().split("\0")
    for name in sorted(paths):
        if not re.fullmatch(r"(?:research|web|web/public-directory)/[A-Za-z0-9_.-]+\.json",name):continue
        raw=subprocess.check_output(["git","show",pin["commit"]+":"+name],cwd=ROOT)
        records.append(archive.bytes_record(name,raw))
    records.sort(key=lambda r:r["path"])
    require(len(records)<=archive.MAX_FILES and sum(x["bytes"] for x in records)<=archive.MAX_TOTAL,"archive bound")
    require({"research/snapshot_release_20261125.json","web/public-directory/manifest.json","web/public-intelligence.json"}<={x["path"] for x in records},"expected app files absent")
    return records

def download_verified(store,name,pin,path):
    before=store.head(name)
    require(before["bytes"]==pin["bytes"],"remote size mismatch")
    h=hashlib.sha256();n=0
    with path.open("xb") as out:
        for part in store.chunks(name,before["etag"]):
            n+=len(part);require(n<=pin["bytes"],"read exceeds pin");h.update(part);out.write(part)
    require(n==pin["bytes"] and h.hexdigest()==pin["sha256"] and store.head(name)==before and sha(path)==pin["sha256"],"remote recovery byte mismatch")
    return before["etag"]

def reconcile_database(root,pin,records):
    by_path={r["path"]:r for r in records}
    expected=pin["reconstruction_audit"]
    a=validate(root,by_path["snapshot/recovery-audit.json"]["sha256"])
    require(a==expected,"restored audit differs from successful reconstruction log")
    db=root/archive.DB
    require(audit_db(db,load_lock(LOCK))==a["table_counts"],"national DB source reconciliation")
    with closing(readonly(db)) as conn:
        check_integrity(conn)
        for table,n in {"iqies_capability_observations":68604,"qies_hospital_service_observations":163176,"iqies_status_observations":100334,"facility_registry_candidate":47169}.items():
            require(conn.execute("SELECT count(*) FROM "+table).fetchone()[0]==n,"derived table count mismatch")
        require(dict(conn.execute("SELECT termination_date_state,count(*) FROM iqies_status_observations GROUP BY termination_date_state"))=={"reported":15803,"ambiguous":9765,"not_available":74766},"status evidence mismatch")
    require(sha(db)==expected["database_sha256"],"recovered DB modified")
    return a

def recover(store,pin,records,root,recovery_run,recovery_commit):
    store.private()
    require(not store.exists(archive.POINTER) and not store.exists(COMPLETE),"receipt or pointer already exists; no overwrite")
    require(len({r["path"] for r in records})==len(records),"duplicate expected payload")
    etags={}
    for r in records:
        name=PAYLOAD+"/"+r["path"]
        archive.allowed_name(name)
        if r["path"].startswith("snapshot/"):
            require(r["path"] in {"snapshot/facilitysignal.sqlite3","snapshot/recovery-audit.json"},"unexpected snapshot path")
            etags[name]=download_verified(store,name,r,root/Path(r["path"]).name)
        else:
            etags[name]=archive.verify(store,name,r)
    inv=verify_inventory(store,PAYLOAD,records,etags)
    a=reconcile_database(root,pin,records)
    require(not store.exists(archive.POINTER) and not store.exists(COMPLETE),"receipt or pointer appeared")
    store.private()
    receipt={"format_version":1,"status":"COMPLETE","domain":"FACILITYSIGNAL_NATIONAL_ARCHIVE","release":RELEASE,"commit":pin["commit"],"payload_prefix":PAYLOAD,"source_records":a["source_records_total"],"database_bytes":a["database_bytes"],"database_sha256":a["database_sha256"],"source_lock_sha256":a["source_lock_sha256"],"file_count":len(records),"total_bytes":sum(r["bytes"] for r in records),"files":records,"sha256_readback":True,"exact_inventory":True,"scope":"Qualified processed national SQLite snapshot plus tracked application and research JSON; no excluded raw owner records, no unqualified source originals, no Pages deployment changes.","recovered_failed_bootstrap_run":pin["run"],"recovery_run":recovery_run,"recovery_commit":recovery_commit,"inventory_etag_audit":inv,"reused_payload_files":len(records),"payload_reuploads":0,"independent_sqlite_restore_verified":True}
    raw=archive.encode(receipt)
    archive.put_bytes(store,COMPLETE,raw)
    verify_inventory(store,PAYLOAD,records,etags)
    store.private()
    pointer={"format_version":1,"domain":receipt["domain"],"release":RELEASE,"commit":pin["commit"],"receipt":COMPLETE,"receipt_sha256":hashlib.sha256(raw).hexdigest(),"source_records":a["source_records_total"]}
    archive.put_bytes(store,archive.POINTER,archive.encode(pointer))
    return receipt

def main():
    p=argparse.ArgumentParser();p.add_argument("--receipt",type=Path,required=True);a=p.parse_args()
    require(not a.receipt.exists(),"receipt exists")
    run,commit=archive.run_key(os.environ)
    pin=load_pin();records=expected_records(pin)
    store=RecoverAzure(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="azure-national-recover-") as d:
            result=recover(store,pin,records,Path(d),run,commit)
        a.receipt.write_bytes(archive.encode(result))
        print("FACILITYSIGNAL_AZURE_RECOVERY_COMPLETE",json.dumps({k:v for k,v in result.items() if k!="files"},sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
