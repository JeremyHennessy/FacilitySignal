"""Verify combined+QCOR preservation, candidate linkage and local backup recovery."""
import argparse
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from build_combined import readonly, require, check_integrity, sha, CORE

PRIOR=CORE+("certification_releases","certification_records")
HOSPITAL=("qcor_hospital_releases","qcor_hospital_current","qcor_hospital_rows")
QUALIFIED_QCOR="0827c681005f3fe61b5e46f6448c3128456b5a7b25b0318738ab764d418c4eec"

def compare(db, path, tables):
    db.execute("ATTACH DATABASE ? AS reference",(path.resolve().as_uri()+"?mode=ro",))
    try:
        counts={}
        for table in tables:
            count=db.execute("SELECT count(*) FROM main."+table).fetchone()[0]
            require(count==db.execute("SELECT count(*) FROM reference."+table).fetchone()[0],"count mismatch "+table)
            for a,b in (("main","reference"),("reference","main")):
                require(db.execute("SELECT 1 FROM (SELECT * FROM "+a+"."+table+" EXCEPT SELECT * FROM "+b+"."+table+") LIMIT 1").fetchone() is None,"row mismatch "+table)
            counts[table]=count
        return counts
    finally:
        db.execute("DETACH DATABASE reference")

def verify(base, final, recovery):
    old=base/"facilitysignal.sqlite3"
    new=final/"facilitysignal.sqlite3"
    cm=json.loads((base/"combined-audit.json").read_text())
    qm=json.loads((final/"qcor-hospital-manifest.json").read_text())
    require(sha(old)==cm["combined_db_sha256"],"combined baseline hash")
    digest=sha(new)
    require(digest==qm["db_sha256"],"integrated hash")
    require(qm["source"]["sha256"]==QUALIFIED_QCOR,"QCOR workbook changed since independent qualification")
    require(qm["stored_rows"]==284391 and qm["rejected_rows"]==0,"QCOR release mismatch")
    with closing(readonly(new)) as db:
        check_integrity(db)
        preserved=compare(db,old,PRIOR)
        require(preserved["facilities"]==cm["preserved_core_rows"]["facilities"],"facility manifest mismatch")
        require(preserved["findings"]==cm["preserved_core_rows"]["findings"],"finding manifest mismatch")
        require(preserved["certification_records"]==sum(cm["registry_rows"].values()),"certification manifest mismatch")
        actual=db.execute("SELECT count(*) FROM qcor_hospital_rows").fetchone()[0]
        require(actual==qm["stored_rows"],"QCOR count mismatch")
        rid=db.execute("SELECT release_id FROM qcor_hospital_current").fetchone()[0]
        require(db.execute("SELECT source_sha256,stored_rows FROM qcor_hospital_releases WHERE id=?",(rid,)).fetchone()==(QUALIFIED_QCOR,actual),"QCOR current release mismatch")
        # Indexed candidate CCNs only, not a resolved site.
        linkage=dict(db.execute("""WITH c AS (SELECT DISTINCT ccn FROM qcor_hospital_rows WHERE release_id=?)
          SELECT 'distinct_qcor_ccns',count(*) FROM c UNION ALL
          SELECT 'exact_care_compare_hospital_family_ccns',count(*) FROM c
          WHERE EXISTS (SELECT 1 FROM facilities f WHERE f.dataset IN ('hospital','rehabilitation','long-term-hospital') AND f.ccn=c.ccn)""",(rid,)))
        linkage["unmatched_care_compare_hospital_family_ccns"]=linkage["distinct_qcor_ccns"]-linkage["exact_care_compare_hospital_family_ccns"]
        require(not recovery.exists(),"recovery output already exists")
        started=time.perf_counter()
        with closing(sqlite3.connect(recovery)) as dest:
            db.backup(dest)
        backup_seconds=round(time.perf_counter()-started,3)
    with closing(readonly(recovery)) as restored:
        check_integrity(restored)
        restored_counts=compare(restored,new,PRIOR+HOSPITAL)
    require(sha(old)==cm["combined_db_sha256"] and sha(new)==digest,"input changed during backup or verification")
    return {"preserved_prior_rows":preserved,"qcor_rows":actual,"source_records_total":preserved["facilities"]+preserved["findings"]+preserved["certification_records"]+actual,"qcor_identifier_candidates":linkage,"db_sha256":digest,"db_bytes":new.stat().st_size,"local_backup_restore":{"seconds":backup_seconds,"bytes":recovery.stat().st_size,"sha256":sha(recovery),"verified_tables":restored_counts},"limitations":["Local ephemeral backup/restore only, not durable hosting.","Exact CCN candidates are not physical-site resolution.","QCOR source publication date and correction unknown; source rows include memo and repeat projections."]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base",type=Path,required=True);p.add_argument("--final",type=Path,required=True);p.add_argument("--recovery",type=Path,required=True)
    a=p.parse_args();audit=verify(a.base,a.final,a.recovery)
    (a.final/"integrated-audit.json").write_text(json.dumps(audit,indent=2)+"\n")
    print("INTEGRATED_VERIFIED",json.dumps(audit),flush=True)
if __name__=="__main__":main()
