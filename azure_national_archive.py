"""Create-only private FacilitySignal national snapshot archive; no Pages changes."""
import argparse,hashlib,io,json,os,re,sqlite3,subprocess
from contextlib import closing
from pathlib import Path,PurePosixPath
from build_combined import sha,require
from restore_snapshot import LOCK,load_lock,audit_db
from private_snapshot_archive import validate,DB,AUDIT,MAX_DB
ROOT=Path(__file__).resolve().parent
ACCOUNT="pharm3r"
CONTAINER="data"
PREFIX="CMS Facility Demo"
POINTER=PREFIX+"/pointers/national-current.json"
MAX_FILES=300
MAX_TOTAL=5*1024**3
def destination(env):
    require(tuple(env.get(k) for k in ("AZURE_STORAGE_ACCOUNT","AZURE_STORAGE_CONTAINER","AZURE_STORAGE_PREFIX"))==(ACCOUNT,CONTAINER,PREFIX),"Azure destination does not match authorized FacilitySignal prefix")
    require(bool(env.get("AZURE_STORAGE_KEY")),"Azure storage secret missing")
def run_key(env):
    require(env.get("GITHUB_REPOSITORY")=="JeremyHennessy/FacilitySignal" and env.get("GITHUB_REF")=="refs/heads/main","live archive restricted to trusted main")
    run,attempt,commit=(env.get(k,"") for k in ("GITHUB_RUN_ID","GITHUB_RUN_ATTEMPT","GITHUB_SHA"))
    require(re.fullmatch(r"[0-9]+",run) and re.fullmatch(r"[0-9]+",attempt) and re.fullmatch(r"[0-9a-f]{40}",commit),"invalid run lineage")
    return "bootstrap-"+run+"-"+attempt,commit
def allowed_name(name):
    require(isinstance(name,str) and name.startswith(PREFIX+"/") and all(x not in ("",".","..") for x in name.split("/")) and not any(ord(x)<32 or x in "\\:" for x in name),"unsafe or foreign blob path")
    require(name==POINTER or re.fullmatch(re.escape(PREFIX)+r"/(?:releases/bootstrap-[0-9]+-[0-9]+/.+|_probes/bootstrap-[0-9]+-[0-9]+\.json)",name),"blob outside authorized release paths")
    return name
def encode(obj):
    return (json.dumps(obj,sort_keys=True,indent=2)+"\n").encode()
def rec(path,file):
    require(file.is_file() and not file.is_symlink(),"archive source must be regular")
    return {"path":path,"bytes":file.stat().st_size,"sha256":sha(file)}
def bytes_record(path,data):
    return {"path":path,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
def verify(store,name,r):
    before=store.head(name);require(before["bytes"]==r["bytes"],"remote size mismatch")
    h=hashlib.sha256();n=0
    for chunk in store.chunks(name,before["etag"]):
        n+=len(chunk);require(n<=r["bytes"],"readback exceeds expected size");h.update(chunk)
    require(n==r["bytes"] and h.hexdigest()==r["sha256"],"remote SHA-256 mismatch")
    require(store.head(name)==before,"remote object changed during readback")
    return before["etag"]
def put_bytes(store,name,data):
    store.create(name,io.BytesIO(data),len(data),"application/json")
    return verify(store,name,bytes_record(name,data))
def preflight(store,run):
    store.private()
    require(not store.exists(POINTER),"national pointer already exists; bootstrap will not replace it")
    name=PREFIX+"/_probes/"+run+".json"
    data=encode({"purpose":"FacilitySignal private storage probe","run":run})
    etag=None
    # Only delete the uniquely created probe, using the ETag of this write.
    etag=store.create(name,io.BytesIO(data),len(data),"application/json")
    try:
        require(verify(store,name,bytes_record(name,data))==etag,"probe ETag changed")
    finally:
        store.delete_probe(name,etag)
    require(not store.exists(name),"probe cleanup not verified")
def check_inventory(store,prefix,records,etags):
    wanted={prefix+"/"+r["path"]:r["bytes"] for r in records}
    parents={str(p) for n in wanted for p in PurePosixPath(n).parents if str(p).startswith(prefix+"/")}
    actual={}
    for v in store.list(prefix):
        name=v["name"];require(name not in actual and name.startswith(prefix+"/"),"invalid inventory")
        if v.get("folder"):
            require(v["bytes"]==0 and name.rstrip("/") in parents and name not in wanted,"unexpected directory marker")
            continue
        actual[name]=v
    require({k:v["bytes"] for k,v in actual.items()}==wanted,"archive inventory mismatch")
    require({k:v["etag"] for k,v in actual.items()}==etags,"archive ETags changed")
def stage(snapshot):
    audit_hash=sha(snapshot/AUDIT)
    a=validate(snapshot,audit_hash)
    lock=load_lock(LOCK)
    require(a["source_lock_sha256"]==sha(LOCK) and a["source_records_total"]==lock["source_records_total"]==1904060,"national release mismatch")
    require(audit_db(snapshot/DB,lock)==a["table_counts"],"national database reconciliation failed")
    with closing(sqlite3.connect((snapshot/DB).resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
        expected={"iqies_capability_observations":68604,"qies_hospital_service_observations":163176,"iqies_status_observations":100334,"facility_registry_candidate":47169}
        for table,n in expected.items():require(db.execute("SELECT count(*) FROM "+table).fetchone()[0]==n,"derived evidence count mismatch")
        require(dict(db.execute("SELECT termination_date_state,count(*) FROM iqies_status_observations GROUP BY termination_date_state"))=={"reported":15803,"ambiguous":9765,"not_available":74766},"status evidence mismatch")
    require(sha(snapshot/DB)==a["database_sha256"] and sha(snapshot/AUDIT)==audit_hash,"snapshot changed")
    files={"snapshot/"+DB:snapshot/DB,"snapshot/"+AUDIT:snapshot/AUDIT}
    # Archive only data JSON already tracked in the repository; never arbitrary files or secrets.
    tracked=subprocess.check_output(["git","ls-files","-z","--","research","web"],cwd=ROOT).decode().split("\0")
    for p in tracked:
        if re.fullmatch(r"(?:research|web|web/public-directory)/[A-Za-z0-9_.-]+\.json",p):
            files[p]=ROOT/p
    require("research/snapshot_release_20261125.json" in files and "web/public-directory/manifest.json" in files,"required data packs missing")
    records=[rec(k,v) for k,v in sorted(files.items())]
    require(len(records)<=MAX_FILES and sum(r["bytes"] for r in records)<=MAX_TOTAL,"archive exceeds bounded transfer")
    return a,files,records
def publish(store,run,commit,snapshot):
    store.private()
    require(not store.exists(POINTER),"bootstrap cannot replace national pointer")
    audit,files,records=stage(snapshot)
    prefix=PREFIX+"/releases/"+run
    payload=prefix+"/files"
    etags={}
    for r in records:
        name=payload+"/"+r["path"];allowed_name(name)
        with files[r["path"]].open("rb") as f:
            store.create(name,f,r["bytes"],"application/json" if name.endswith(".json") else "application/octet-stream")
        etags[name]=verify(store,name,r)
        require(sha(files[r["path"]])==r["sha256"],"local payload changed")
    check_inventory(store,payload,records,etags)
    # The exact database bytes were read back and match the independently checked local database.
    receipt={"format_version":1,"status":"COMPLETE","domain":"FACILITYSIGNAL_NATIONAL_ARCHIVE","release":run,"commit":commit,"payload_prefix":payload,"source_records":audit["source_records_total"],"database_bytes":audit["database_bytes"],"database_sha256":audit["database_sha256"],"source_lock_sha256":audit["source_lock_sha256"],"file_count":len(records),"total_bytes":sum(r["bytes"] for r in records),"files":records,"sha256_readback":True,"exact_inventory":True,"scope":"Qualified processed national SQLite snapshot plus tracked application and research JSON; no excluded raw owner records, no unqualified source originals, no Pages deployment changes."}
    receipt_name=prefix+"/complete.json";data=encode(receipt)
    put_bytes(store,receipt_name,data)
    check_inventory(store,payload,records,etags)
    store.private()
    pointer={"format_version":1,"domain":receipt["domain"],"release":run,"commit":commit,"receipt":receipt_name,"receipt_sha256":hashlib.sha256(data).hexdigest(),"source_records":audit["source_records_total"]}
    put_bytes(store,POINTER,encode(pointer))
    return receipt
class Azure:
    def __init__(self,env):
        destination(env)
        from azure.storage.blob import BlobServiceClient
        self.service=BlobServiceClient("https://"+ACCOUNT+".blob.core.windows.net",credential=env["AZURE_STORAGE_KEY"],retry_total=3,connection_timeout=15,read_timeout=120,max_single_get_size=8*1024**2,max_chunk_get_size=4*1024**2)
        self.container=self.service.get_container_client(CONTAINER)
    def private(self):
        p=self.container.get_container_properties()
        require(p.public_access in (None,""),"container permits anonymous access; refusing storage")
    def blob(self,n):return self.container.get_blob_client(allowed_name(n))
    def exists(self,n):return self.blob(n).exists()
    def head(self,n):
        p=self.blob(n).get_blob_properties()
        return {"bytes":p.size,"etag":str(p.etag)}
    def chunks(self,n,etag):
        from azure.core import MatchConditions
        yield from self.blob(n).download_blob(etag=etag,match_condition=MatchConditions.IfNotModified,max_concurrency=1).chunks()
    def create(self,n,stream,size,kind):
        from azure.storage.blob import ContentSettings
        r=self.blob(n).upload_blob(stream,length=size,overwrite=False,max_concurrency=1,content_settings=ContentSettings(content_type=kind,cache_control="private, no-store"))
        return str(r["etag"])
    def delete_probe(self,n,etag):
        from azure.core import MatchConditions
        require(re.fullmatch(re.escape(PREFIX)+r"/_probes/bootstrap-[0-9]+-[0-9]+\.json",n) and bool(etag),"probe deletion only")
        self.blob(n).delete_blob(etag=etag,match_condition=MatchConditions.IfNotModified)
    def list(self,prefix):
        allowed_name(prefix)
        for p in self.container.list_blobs(name_starts_with=prefix+"/",include=["metadata"]):
            yield {"name":p.name,"bytes":p.size,"etag":str(p.etag),"folder":str((p.metadata or {}).get("hdi_isfolder","")).lower()=="true"}
    def close(self):self.service.close()
def main():
    p=argparse.ArgumentParser();p.add_argument("operation",choices=("probe","publish"));p.add_argument("--snapshot",type=Path);p.add_argument("--receipt",type=Path);a=p.parse_args()
    run,commit=run_key(os.environ)
    store=Azure(os.environ)
    try:
        if a.operation=="probe":
            preflight(store,run)
            print("PRIVATE_BLOB_PROBE_PASS",flush=True)
        else:
            require(a.snapshot is not None and a.receipt is not None,"snapshot and receipt required")
            result=publish(store,run,commit,a.snapshot)
            with a.receipt.open("x") as f:json.dump(result,f,indent=2,sort_keys=True)
            print("FACILITYSIGNAL_AZURE_ARCHIVE_COMPLETE",json.dumps({k:v for k,v in result.items() if k!="files"},sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":
    main()
