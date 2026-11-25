"""Build an isolated combined CMS snapshot; prove the source collections remain separate."""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path
import facilitysignal as fs

CORE = ("releases", "current_release", "facilities", "findings")
REGISTRIES = {"qies", "iqies", "clia"}

def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def read_manifest(folder, filename):
    return json.loads((folder / filename).read_text(encoding="utf-8"))

def readonly(path):
    if not path.is_file():
        raise ValueError("snapshot database missing")
    return sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True)

def require(condition, message):
    if not condition:
        raise ValueError(message)

def check_integrity(db):
    require(db.execute("PRAGMA integrity_check").fetchall()==[("ok",)],"integrity check failed")
    require(not db.execute("PRAGMA foreign_key_check").fetchone(),"foreign key check failed")

def validate_base(folder):
    db_path=folder/"facilitysignal.sqlite3"
    manifest=read_manifest(folder,"manifest.json")
    require(sha(db_path)==manifest["db_sha256"],"CMS base hash mismatch")
    with closing(readonly(db_path)) as db:
        check_integrity(db)
        releases=dict(db.execute("SELECT c.dataset,r.stored_rows FROM current_release c JOIN releases r ON r.id=c.release_id"))
        require(set(releases)==set(fs.CATALOG),"CMS base must contain all nine releases")
        for table,keys,metric in (("facilities",fs.FACILITY_DATASETS,"facility_records"),("findings",fs.FINDING_DATASETS,"finding_records")):
            actual=dict(db.execute("SELECT dataset,count(*) FROM "+table+" GROUP BY dataset"))
            require(actual=={k:releases[k] for k in keys},"CMS "+table+" reconciliation")
            require(sum(actual.values())==manifest[metric],"CMS "+metric+" manifest reconciliation")
        require(len(manifest["sources"])==len(releases),"CMS source manifest count")
        by_key={x["dataset"]:x for x in manifest["sources"]}
        require(set(by_key)==set(releases),"CMS source manifest keys")
        for dataset,digest,n in db.execute("SELECT c.dataset,r.sha256,r.input_rows FROM current_release c JOIN releases r ON r.id=c.release_id"):
            item=by_key[dataset]
            require(item["sha256"]==digest and item["expected_rows"]==n,"CMS source checksum/count mismatch")
    return manifest

def verify(base, candidate):
    base=base.resolve()
    candidate=candidate.resolve()
    require(base!=candidate,"base and candidate must differ")
    cms=validate_base(base)
    registry=read_manifest(candidate,"registry-manifest.json")
    db_path=candidate/"facilitysignal.sqlite3"
    combined_hash=sha(db_path)
    require(combined_hash==registry["db_sha256"],"combined candidate hash mismatch")
    with closing(readonly(db_path)) as db:
        check_integrity(db)
        db.execute("ATTACH DATABASE ? AS baseline",((base/"facilitysignal.sqlite3").as_uri()+"?mode=ro",))
        preserved={}
        for table in CORE:
            n=db.execute("SELECT count(*) FROM main."+table).fetchone()[0]
            old=db.execute("SELECT count(*) FROM baseline."+table).fetchone()[0]
            require(n==old,"baseline row count changed: "+table)
            for a,b in (("main","baseline"),("baseline","main")):
                sql="SELECT 1 FROM (SELECT * FROM "+a+"."+table+" EXCEPT SELECT * FROM "+b+"."+table+") LIMIT 1"
                require(db.execute(sql).fetchone() is None,"baseline rows changed: "+table)
            preserved[table]=n
        actual=dict(db.execute("SELECT registry,count(*) FROM certification_records GROUP BY registry"))
        declared=dict(db.execute("SELECT registry,row_count FROM certification_releases"))
        sources={x["registry"]:x for x in registry["sources"]}
        require(set(actual)==REGISTRIES and set(sources)==REGISTRIES and len(registry["sources"])==3,"registry source coverage")
        require(actual==declared=={k:x["rows"] for k,x in sources.items()},"registry row reconciliation")
        require(sum(actual.values())==registry["certification_records"],"registry total reconciliation")
        for key,digest in db.execute("SELECT registry,source_sha256 FROM certification_releases"):
            item=sources[key]
            require(digest==item["sha256"],"registry source hash mismatch")
            suffix=".zip" if item["source"]["zipped"] else ".csv"
            require(sha(candidate/"raw"/(key+suffix))==digest,"retained registry original hash mismatch")
        # Compare identifiers only to characterize potential crosswalk work.
        # CLIA numbers are not Medicare CCNs. No site, operator or active status is inferred.
        candidates=[dict(zip(("registry","identifier_matches","same_state_candidates","different_or_missing_state_candidates"),row)) for row in db.execute("""
            WITH per_registry AS (
                SELECT c.registry,c.row_number,
                       MAX(CASE WHEN f.state=c.state AND c.state<>'' THEN 1 ELSE 0 END) AS same_state
                FROM facilities f CROSS JOIN certification_records c INDEXED BY certification_id ON c.provider_id=f.ccn
                WHERE c.registry IN ('qies','iqies') AND c.provider_id<>''
                GROUP BY c.registry,c.row_number
            )
            SELECT registry,count(*),sum(same_state),sum(1-same_state)
            FROM per_registry GROUP BY registry ORDER BY registry
        """)]
        times={}
        for label,query,args in (
            ("facility_state_page","SELECT * FROM facilities WHERE state=? ORDER BY name COLLATE NOCASE LIMIT 25",("CA",)),
            ("finding_ccn","SELECT * FROM findings WHERE ccn=(SELECT ccn FROM facilities WHERE dataset='nursing' LIMIT 1) ORDER BY survey_date DESC LIMIT 25",()),
            ("registry_state_page","SELECT * FROM certification_records WHERE state=? AND registry=? ORDER BY name COLLATE NOCASE LIMIT 25",("CA","clia")),
            ("registry_substring_count","SELECT count(*) FROM certification_records WHERE name LIKE ?",("%hospital%",)),
        ):
            samples=[]
            for _ in range(3):
                started=time.perf_counter()
                db.execute(query,args).fetchall()
                samples.append(round(1000*(time.perf_counter()-started),3))
            times[label]=samples
    require(sha(base/"facilitysignal.sqlite3")==cms["db_sha256"],"base changed during verification")
    require(sha(db_path)==combined_hash,"combined candidate changed during verification")
    return {"base_db_sha256":cms["db_sha256"],"combined_db_sha256":combined_hash,
            "preserved_core_rows":preserved,"registry_rows":actual,
            "combined_source_records":preserved["facilities"]+preserved["findings"]+sum(actual.values()),
            "identifier_overlap_audit":candidates,"query_samples_ms":times,"db_bytes":db_path.stat().st_size,
            "limitations":["Identifier overlaps are candidates, not resolved canonical facilities.",
                           "Query timings are single-process SQLite measurements, not production SLA or concurrency results.",
                           "Registry status interpretation and persistent storage are not qualified."]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cms-base",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    base=args.cms_base.resolve()
    out=args.output.resolve()
    require(not out.exists(),"output must be new")
    validate_base(base)
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".combined-stage-",dir=out.parent) as tmp:
        stage=Path(tmp)/"candidate"
        subprocess.run([sys.executable,str(Path(__file__).with_name("collect_registry.py")),
                        "--base-db",str(base/"facilitysignal.sqlite3"),"--output",str(stage)],check=True)
        audit=verify(base,stage)
        shutil.copyfile(base/"manifest.json",stage/"cms-manifest.json")
        (stage/"combined-audit.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        os.rename(stage,out)
        print("COMBINED_VERIFIED",json.dumps(audit),flush=True)

if __name__=="__main__":
    main()
