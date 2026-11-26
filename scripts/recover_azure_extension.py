"""Verify exact existing extension upload and create only its missing pointer."""
import argparse,json,os,re,sqlite3,tempfile
from contextlib import closing
from pathlib import Path
import azure_national_archive as archive
from scripts import azure_verified_extension as ext
from scripts.azure_inventory import verify_inventory
from build_combined import require,sha,readonly,check_integrity
from scripts.verify_expanded_source_archive import load_lock

ROOT=Path(__file__).resolve().parents[1]
PIN=ROOT/"research/azure_extension_recovery_pin_20261126.json"
RELEASE="extension-45847822268-1"
COMMIT="320ac454b01412025886ba3935757c36f90a74e6"
PREFIX=archive.PREFIX+"/releases/"+RELEASE
PAYLOAD=PREFIX+"/files"
COMPLETE=PREFIX+"/complete.json"
class RecoveryAzure(ext.ExtensionAzure):
    def create(self,name,stream,size,kind):
        require(name==ext.EXT_POINTER,"only absent extension pointer may be created")
        return super().create(name,stream,size,kind)

def load_pin():
    p=json.loads(PIN.read_text())
    require(p["format_version"]==1 and p["run"]==45847822268 and p["attempt"]==1 and p["release"]==RELEASE and p["commit"]==COMMIT and len(p["source_log_results"])==15,"extension recovery pin")
    return p

def validate_receipt(receipt,national,pin):
    require(receipt["format_version"]==1 and receipt["domain"]==ext.EXT_DOMAIN and receipt["status"]=="COMPLETE" and receipt["release"]==RELEASE and receipt["commit"]==COMMIT and receipt["payload_prefix"]==PAYLOAD,"extension receipt identity")
    require(receipt["base_release"]==national["pointer"]["release"]==pin["base_release"] and receipt["base_receipt_sha256"]==national["receipt_sha256"] and receipt["base_pointer_sha256"]==national["pointer_sha256"],"extension base lineage")
    require(national["receipt"]["database_sha256"]==pin["base_database_sha256"] and receipt["base_source_records"]==1904060,"base DB pin")
    require(receipt["source_records"]==ext.EXPECTED_ROWS and receipt["source_count"]==16 and receipt["sha256_readback"] is True and receipt["exact_inventory"] is True and receipt["application_pack_parity"]==pin["app_parity"],"extension receipt counts or parity")
    records=receipt["files"]
    require(len(records)==receipt["file_count"]==3 and {r["path"] for r in records}=={"extension.sqlite3","extension-audit.json","expanded-source-lock.json"},"extension file scope")
    require(sum(r["bytes"] for r in records)==receipt["total_bytes"]<=ext.MAX_TOTAL,"extension file size")
    for r in records:
        require(type(r["bytes"]) is int and r["bytes"]>0 and re.fullmatch(r"[a-f0-9]{64}",r["sha256"]),"invalid payload pin")
    db=next(r for r in records if r["path"]=="extension.sqlite3")
    require(db["sha256"]==receipt["database_sha256"] and db["bytes"]==receipt["database_bytes"]<=ext.MAX_DB,"extension database pin")
    return records

def verify_db(db_path,audit,receipt,pin,base):
    lock=load_lock();pins={x["source_id"]:x for x in lock["expanded_sources"] if x["source_id"]!="FS-009"}
    require(audit["source_records"]==ext.EXPECTED_ROWS and audit["source_count"]==16 and audit["base_database_sha256"]==sha(base)==pin["base_database_sha256"] and audit["database_sha256"]==sha(db_path)==receipt["database_sha256"] and audit["database_bytes"]==db_path.stat().st_size==receipt["database_bytes"],"extension database/audit identity")
    require(audit["application_pack_parity"]==pin["app_parity"] and audit["hrsa_row_level_records"]==0 and set(audit["sources"])==set(pins),"extension scope")
    require(all(audit["sources"][k]==v for k,v in pin["source_log_results"].items()),"original job log source evidence mismatch")
    with closing(readonly(db_path)) as db,closing(readonly(base)) as old:
        check_integrity(db)
        lineage={r[0]:tuple(r[1:]) for r in db.execute("SELECT source_id,table_name,source_sha256,source_bytes,rows,qualification_run FROM extension_sources")}
        expected={sid:(audit["sources"][sid]["table"],p["sha256"],p["bytes"],p["qualified_rows"],p["qualification_run"]) for sid,p in pins.items()}
        require(lineage==expected,"extension source lineage mismatch")
        require(sum(v[3] for v in lineage.values())==ext.EXPECTED_ROWS,"extension total")
        for sid,table in ((k,v[0]) for k,v in lineage.items()):
            if table=="qcor_provider_rows":
                p=pins[sid];a=audit["sources"][sid]
                n=db.execute("SELECT count(*) FROM qcor_provider_rows WHERE source_id=?",(sid,)).fetchone()[0]
                providers=db.execute("SELECT count(DISTINCT ccn) FROM qcor_provider_rows WHERE source_id=?",(sid,)).fetchone()[0]
                events=db.execute("SELECT count(*) FROM (SELECT DISTINCT ccn,event,day FROM qcor_provider_rows WHERE source_id=?)",(sid,)).fetchone()[0]
                require(n==p["qualified_rows"] and providers==a["distinct_source_provider_keys"] and events==a["source_event_keys"],"QCOR source/event mismatch")
            else:
                require(table in {"penalty","hospital_cost_report","snf_cost_report","inspection_dates","survey_summary","mqsa_projection"},"unexpected extension table")
                require(db.execute("SELECT count(*) FROM "+table).fetchone()[0]==pins[sid]["qualified_rows"],"extension table row count")
        require(db.execute("SELECT count(*) FROM qcor_provider_rows").fetchone()[0]==ext.QCOR_ROWS,"QCOR total")
        require(db.execute("SELECT count(*) FROM mqsa_projection WHERE schema_exception='width_address1'").fetchone()[0]==6,"FDA width exceptions")
        require({x[1] for x in db.execute("PRAGMA table_info(mqsa_projection)")}=={"ordinal","name","address1","address2","address3","city","state","zip","schema_exception"},"FDA projection scope")
        require(ext.cms.surveys.compare_dates(db,old)=={"same_ccn_day":619069},"citation crosscheck")
    require(sha(base)==pin["base_database_sha256"] and sha(db_path)==receipt["database_sha256"],"restored data changed")
    return {"source_records":ext.EXPECTED_ROWS,"source_count":16,"citation_ccn_day_crosscheck":619069,"sqlite_integrity":"passed","source_lineage_verified":True}

def recover(store,root,pin):
    national=ext.national_manifest(store)
    require(not store.exists(ext.EXT_POINTER),"extension pointer exists; never overwrite")
    receipt,receipt_sha,receipt_head=ext.read_small(store,COMPLETE)
    records=validate_receipt(receipt,national,pin)
    base,_=ext.restore_national(store,national,root/"national")
    parity=ext.verify_application_packs(store,national)
    require(parity==pin["app_parity"],"Pages application pack parity")
    etags={}
    for r in records:
        name=PAYLOAD+"/"+r["path"]
        ext.fetch_verified(store,name,r,root/r["path"])
        etags[name]=store.head(name)["etag"]
    inv=verify_inventory(store,PAYLOAD,records,etags)
    require(sha(root/"expanded-source-lock.json")==sha(ROOT/"research/expanded_source_lock_20261126.json"),"expanded source lock differs")
    audit=json.loads((root/"extension-audit.json").read_text())
    validation=verify_db(root/"extension.sqlite3",audit,receipt,pin,base)
    verify_inventory(store,PAYLOAD,records,etags)
    ext.unchanged(store,national)
    require(store.head(COMPLETE)==receipt_head and ext.read_small(store,COMPLETE,receipt_sha)[0]==receipt,"extension receipt changed")
    pointer={"format_version":1,"domain":ext.EXT_DOMAIN,"release":RELEASE,"commit":COMMIT,"base_release":receipt["base_release"],"base_receipt_sha256":receipt["base_receipt_sha256"],"receipt":COMPLETE,"receipt_sha256":receipt_sha,"source_records":ext.EXPECTED_ROWS}
    archive.put_bytes(store,ext.EXT_POINTER,archive.encode(pointer))
    ext.unchanged(store,national)
    return {**validation,"release":RELEASE,"base_release":receipt["base_release"],"receipt_sha256":receipt_sha,"database_sha256":receipt["database_sha256"],"database_bytes":receipt["database_bytes"],"file_count":receipt["file_count"],"total_bytes":receipt["total_bytes"],"payload_reuploads":0,"inventory_etag_audit":inv,"application_pack_parity":parity,"status":"COMPLETE","pointer_verified":True,"prior_failed_run":45847822268}

def main():
    p=argparse.ArgumentParser();p.add_argument("--receipt",type=Path,required=True);a=p.parse_args()
    require(not a.receipt.exists(),"receipt exists")
    archive.run_key(os.environ);store=RecoveryAzure(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="extension-recovery-") as d:result=recover(store,Path(d),load_pin())
        a.receipt.write_bytes(archive.encode(result))
        print("FACILITYSIGNAL_AZURE_EXTENSION_RECOVERY_COMPLETE",json.dumps(result,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
