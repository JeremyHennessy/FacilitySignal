"""Private, minimal Type-2 NPI key archive pilot; never an active-provider directory."""
import argparse,json,os,re,sqlite3,tempfile
from contextlib import closing
from pathlib import Path
import azure_national_archive as archive
from build_combined import require,sha,check_integrity,readonly
from scripts import qualify_nppes_v2 as nppes
from scripts.azure_verified_extension import national_manifest,unchanged,read_small,EXT_POINTER
from scripts.azure_inventory import verify_inventory

ROOT=Path(__file__).resolve().parents[1]
PREFIX=archive.PREFIX+"/nppes-organization-key-pilot"
PIN="d0e73f9d00ee816d1053d9c1005bd429183b13fce3ebf55bc2fde382274d2897"
COUNT=6627
LIMIT=2*1024**2
def safe_name(name):
    require(re.fullmatch(re.escape(PREFIX)+"/"+PIN+r"(?:/files(?:/(?:organizations\.sqlite3|audit\.json))?|/complete\.json)",name) is not None,"outside NPPES pilot namespace")
    return name
class PilotAzure(archive.Azure):
    def blob(self,name):
        if name==EXT_POINTER:return self.container.get_blob_client(name)
        if name.startswith(PREFIX+"/"):safe_name(name)
        else:archive.allowed_name(name)
        return self.container.get_blob_client(name)
    def create(self,name,stream,size,kind):
        safe_name(name)
        require("/files/" in name or name.endswith("/complete.json"),"invalid write path")
        return super().create(name,stream,size,kind)
    def delete_probe(self,name,etag):raise ValueError("pilot never deletes")
    def list(self,prefix):
        safe_name(prefix)
        for p in self.container.list_blobs(name_starts_with=prefix+"/",include=["metadata"]):
            yield {"name":p.name,"bytes":p.size,"etag":str(p.etag),"folder":str((p.metadata or {}).get("hdi_isfolder","")).lower()=="true"}
def validate_db(path,count):
    require(path.is_file() and not path.is_symlink() and 0<path.stat().st_size<=LIMIT,"key database size")
    with closing(readonly(path)) as db:
        check_integrity(db)
        require(db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()==[("table","organizations")],"unexpected objects")
        require(db.execute("PRAGMA table_info(organizations)").fetchall()==[(0,"npi","TEXT",1,None,1)],"unexpected fields")
        rows=0
        for (key,) in db.execute("SELECT npi FROM organizations"):
            require(nppes.npi_valid(key),"invalid organization key");rows+=1
        require(rows==count,"key reconciliation")
    return {"organization_keys":rows,"database_sha256":sha(path),"database_bytes":path.stat().st_size,"integrity":"passed"}
def qualify(root):
    ledger=json.loads((ROOT/"research/coverage_status.json").read_text())
    old=ledger["nppes_v2_qualified_baselines"]["weekly"]["audit"]
    require(old["publisher"]["sha256"]==PIN and old["distinct_valid_organization_npis"]==COUNT,"qualified pin mismatch")
    path=root/"source.zip";db=root/"organizations.sqlite3"
    meta=nppes.download(path,"weekly",publisher_label=old["publisher_label"])
    require(all(meta[k]==old["publisher"][k] for k in ("url","bytes","sha256")),"source changed")
    result=nppes.inspect(path,db,"weekly")
    for k,v in result.items():require(v==old[k],"prior qualification differs: "+k)
    require(sha(path)==PIN,"source changed during processing")
    return {"source_id":"FS-004","publisher":meta,"release_label":old["publisher_label"],
        "qualification_run":45832460359,"source_input_rows":result["input_rows"],
        "entity_classes":result["entity_classes"],"key_database":validate_db(db,COUNT),
        "scope":"Independent weekly Type-2 registration keys only. No names, contacts, addresses, taxonomy, endpoint values or former deactivated identities; not an active-provider or physical-site count.",
        "public_promotion":False,"commercial_reuse_review":"pending"}
def publish(store,root,audit,national,extension_head):
    store.private()
    prefix=PREFIX+"/"+PIN;payload=prefix+"/files";receipt_name=prefix+"/complete.json"
    def stable():
        unchanged(store,national)
        require(store.head(EXT_POINTER)==extension_head,"extension pointer changed")
    stable()
    db=root/"organizations.sqlite3"
    require(validate_db(db,COUNT)==audit["key_database"],"database changed")
    ap=root/"audit.json";ap.write_bytes(archive.encode(audit))
    files={"organizations.sqlite3":db,"audit.json":ap}
    records=[archive.rec(k,v) for k,v in sorted(files.items())]
    require(not store.exists(receipt_name),"pilot already exists; do not replace")
    etags={}
    for pin in records:
        name=payload+"/"+pin["path"];safe_name(name)
        require(not store.exists(name),"existing incomplete payload requires separate recovery")
        with files[pin["path"]].open("rb") as f:store.create(name,f,pin["bytes"],"application/json" if name.endswith(".json") else "application/octet-stream")
        etags[name]=archive.verify(store,name,pin)
    inventory=verify_inventory(store,payload,records,etags)
    stable()
    receipt={"status":"COMPLETE","domain":"FACILITYSIGNAL_NPPES_PRIVATE_KEY_PILOT","format_version":1,"source_sha256":PIN,"organization_keys":COUNT,"base_release":national["pointer"]["release"],"files":records,"inventory":inventory,"sha256_readback":True,"public_promotion":False}
    archive.put_bytes(store,receipt_name,archive.encode(receipt))
    stable()
    return receipt
def main():
    p=argparse.ArgumentParser();p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    archive.run_key(os.environ)
    store=PilotAzure(os.environ)
    try:
        national=national_manifest(store);ext=store.head(EXT_POINTER)
        with tempfile.TemporaryDirectory(prefix="nppes-key-pilot-") as d:
            root=Path(d);result=qualify(root)
            receipt=publish(store,root,result,national,ext)
        with a.audit.open("x") as f:json.dump({"audit":result,"receipt":receipt},f,indent=2);f.write("\n")
    finally:store.close()
if __name__=="__main__":main()
