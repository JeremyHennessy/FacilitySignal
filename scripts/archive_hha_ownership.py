"""Qualify and privately persist a new official HHA ownership release.

Reuse PECOS organizational projection. Do not retain individual owners, personal
owner identifiers, addresses, individual names or raw source files.
"""
import argparse,json,os,sqlite3,tempfile
from contextlib import closing
from pathlib import Path
import azure_national_archive as a
import collect_registry as registry
import collect_ownership as ownership
from probe_ownership import select
from scripts import azure_source_archive as storage
from build_combined import require,sha,check_integrity
TITLE="Home Health Agency All Owners"
VERSION="87e65a9e-3695-4b48-bd5c-4d5f4dfc7f08"
EXPECTED=102942
COLUMNS=38
KEY="hha-owner"
ARCHIVE_KEY="hha-organizational-ownership"
def selection(catalog):
    m=select(catalog,TITLE)
    require(m["api"]=="https://data.cms.gov/data-api/v1/dataset/"+VERSION+"/data","publisher version differs")
    require(len(m["distributions"])==1 and m["distributions"][0]["format"]=="CSV","CSV distribution scope")
    return {**m,"url":m["distributions"][0]["url"],"zipped":False}

def project(path,db_path,meta,digest,expected,columns):
    with closing(sqlite3.connect(db_path)) as db:
        ownership.init(db)
        out=ownership.ingest(db,KEY,meta,path,digest,expected)
        require(len(out["columns"])==columns and len(set(out["columns"]))==columns,"publisher schema width changed")
        require(out["input_rows"]==expected==out["stored_rows"]+out["excluded_individual_rows"] and out["rejected_rows"]==0 and out["stored_rows"]>0,"ownership reconciliation")
        require(not out["identifier_quality_flags"],"unresolved enrollment or owner ID format")
        # Enforce institutional-only projection schema independently.
        require(not db.execute("SELECT 1 FROM pecos_org_role_rows WHERE source<>? LIMIT 1",(KEY,)).fetchone(),"unexpected source")
        fields=set(ownership.ORG)
        for (raw,) in db.execute("SELECT projection FROM pecos_org_role_rows"):
            require(set(json.loads(raw))==fields,"projection field boundary")
        require(db.execute("SELECT count(*) FROM pecos_enrollment_rows").fetchone()[0]==db.execute("SELECT count(*) FROM pecos_chow_rows").fetchone()[0]==0,"unrelated rows")
        summary={"source_id":"FS-049","input_rows":expected,"organization_role_rows":out["stored_rows"],"excluded_individual_rows":out["excluded_individual_rows"],"rejected_rows":out["rejected_rows"],"source_columns":columns,"distinct_enrollment_ids":db.execute("SELECT count(DISTINCT enrollment_id) FROM pecos_org_role_rows").fetchone()[0],"distinct_owner_pac_ids":db.execute("SELECT count(DISTINCT owner_pac_id) FROM pecos_org_role_rows").fetchone()[0],"role_code_counts":dict(db.execute("SELECT role_code,count(*) FROM pecos_org_role_rows GROUP BY role_code")),"individual_rows_retained":0,"linkage":"Enrollment and PAC keys retained; no HHA enrollment crosswalk or physical ownership inference.","public_promotion":False}
        require(sum(summary["role_code_counts"].values())==summary["organization_role_rows"],"role reconciliation")
        check_integrity(db)
    return summary

def main():
    p=argparse.ArgumentParser();p.add_argument("--receipt",type=Path,required=True);args=p.parse_args();require(not args.receipt.exists(),"receipt exists")
    a.run_key(os.environ);store=storage.SourceAzure(os.environ)
    try:
        national=storage.national_manifest(store)
        meta=selection(registry.get_json(registry.CATALOG));require(registry.expected_rows(meta)==EXPECTED,"API count changed")
        # API sample schema only, never print values.
        sample=registry.get_json(meta["api"]+"?size=1")
        require(isinstance(sample,list) and len(sample)==1 and len(sample[0])==COLUMNS and set(ownership.ORG+("TYPE - OWNER",))<=set(sample[0]),"API schema mismatch")
        with tempfile.TemporaryDirectory(prefix="hha-owner-archive-") as d:
            root=Path(d);source=root/"source.csv"
            digest,size=registry.download(meta,source)
            require(0<size<=80_000_000 and sha(source)==digest,"source bytes")
            publisher={**meta,"sha256":digest,"bytes":size}
            receipt=storage.existing(store,ARCHIVE_KEY,digest)
            if receipt is None:
                db=root/"projection.sqlite3";summary=project(source,db,meta,digest,EXPECTED,COLUMNS)
                require(registry.expected_rows(meta)==EXPECTED and selection(registry.get_json(registry.CATALOG))==meta and sha(source)==digest,"publisher changed during qualification")
                source.unlink()
                audit={"publisher":publisher,"summary":summary,"projection_sha256":sha(db),"projection_bytes":db.stat().st_size,"reuse_review":"pending","limits":"Self-reported PECOS organizational roles, not deed ownership. No individual owner rows, raw files or public data promotion."}
                receipt=storage.publish(store,ARCHIVE_KEY,publisher,db,audit,root,national)
        args.receipt.write_bytes(a.encode(receipt))
        print("PRIVATE_NEW_HHA_OWNERSHIP_COMPLETE",json.dumps(receipt,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
