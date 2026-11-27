"""Local-only compact iQIES extension recovery, bound to an exact national base.

No network, archive writes, public exports or pointer changes. A receipt and
sidecar must remain in authorized private storage; never place them in web/.
"""
import argparse
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from build_combined import require, readonly, sha, check_integrity
from iqies_additional_services import DDL, RULES
from scripts.qualify_iqies_national_services import preservation, service_checks

TABLES = ("iqies_additional_service_release", "iqies_additional_service_observations")
RECEIPT = Path(__file__).resolve().parents[1] / "research/iqies_national_service_qualification_20261127.json"

def pinned_receipt():
    return json.loads(RECEIPT.read_text())["receipt"]

def validate_rows(db, schema, expected):
    rows = dict(db.execute("SELECT value_state,count(*) FROM "+schema+"."+TABLES[1]+" GROUP BY value_state"))
    require(rows == expected["service_states"], "sidecar state mismatch")
    grouped = {}
    for f, scope, state, count in db.execute("SELECT field,provider_scope,value_state,count(*) FROM "+schema+"."+TABLES[1]+" GROUP BY field,provider_scope,value_state"):
        require(f in RULES and RULES[f][0] == scope, "sidecar provider scope")
        grouped.setdefault(f,{})[state]=count
    require(grouped == expected["field_states"], "sidecar field mismatch")
    rel = db.execute("SELECT * FROM "+schema+"."+TABLES[0]).fetchall()
    require([tuple(x) for x in rel] == [(1,expected["source_sha256"],expected["dictionary_sha256"],expected["source_period"],expected["verified_source_rows"])], "sidecar release mismatch")

def compare_rows(db, left, right):
    for t in TABLES:
        for a,b in ((left,right),(right,left)):
            require(db.execute("SELECT 1 FROM (SELECT * FROM "+a+"."+t+" EXCEPT SELECT * FROM "+b+"."+t+") LIMIT 1").fetchone() is None, "extension rows differ")
        require(db.execute("SELECT count(*) FROM "+left+"."+t).fetchone() == db.execute("SELECT count(*) FROM "+right+"."+t).fetchone(), "extension count differs")

def export(base, candidate, output):
    expected=pinned_receipt()
    require(sha(base)==expected["base_database_sha256"] and sha(candidate)==expected["database_sha256"],"qualified database pin mismatch")
    require(preservation(base,candidate)==expected["unchanged_base_table_counts"],"base preservation mismatch")
    require(not output.exists(),"output already exists")
    with tempfile.TemporaryDirectory(dir=output.parent,prefix=".service-sidecar-") as tmp:
        ready=Path(tmp)/"ready"; ready.mkdir(mode=0o700)
        pack=ready/"services.sqlite3"
        with closing(sqlite3.connect(pack)) as db:
            # A standalone sidecar has no certification table. Its foreign
            # key is enforced only when restored into the pinned national DB.
            db.executescript(DDL)
            db.execute("ATTACH DATABASE ? AS candidate",(candidate.resolve().as_uri()+"?mode=ro&immutable=1",))
            for t in TABLES:
                db.execute("INSERT INTO "+t+" SELECT * FROM candidate."+t)
            validate_rows(db,"main",expected)
            compare_rows(db,"main","candidate")
            db.commit()
        manifest={"format_version":1,"base_database_sha256":sha(base),"qualified_candidate_sha256":sha(candidate),"sidecar_sha256":sha(pack),"sidecar_bytes":pack.stat().st_size,"observations":expected["observations"]}
        (ready/"manifest.json").write_text(json.dumps(manifest,sort_keys=True)+"\n")
        ready.rename(output)
    return manifest

def restore(base, sidecar, output, manifest_sha256):
    expected=pinned_receipt()
    require(sha(sidecar/"manifest.json")==manifest_sha256,"trusted manifest pin mismatch")
    manifest=json.loads((sidecar/"manifest.json").read_text())
    pack=sidecar/"services.sqlite3"
    require(manifest=={"format_version":1,"base_database_sha256":expected["base_database_sha256"],"qualified_candidate_sha256":expected["database_sha256"],"sidecar_sha256":sha(pack),"sidecar_bytes":pack.stat().st_size,"observations":expected["observations"]},"sidecar manifest mismatch")
    require(sha(base)==expected["base_database_sha256"],"base pin mismatch")
    require(not output.exists(),"output already exists")
    with tempfile.TemporaryDirectory(dir=output.parent,prefix=".service-restore-") as tmp:
        dest=Path(tmp)/"restored.sqlite3"
        with closing(readonly(base)) as src, closing(sqlite3.connect(dest)) as db:
            src.backup(db)
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("ATTACH DATABASE ? AS sidecar",(pack.resolve().as_uri()+"?mode=ro&immutable=1",))
            validate_rows(db,"sidecar",expected)
            db.executescript("BEGIN IMMEDIATE;\n"+DDL)
            for t in TABLES:
                db.execute("INSERT INTO "+t+" SELECT * FROM sidecar."+t)
            compare_rows(db,"main","sidecar")
            check_integrity(db)
            db.commit()
        require(preservation(base,dest)==expected["unchanged_base_table_counts"],"restored baseline differs")
        service_checks(dest,expected["field_states"])
        require(sha(base)==expected["base_database_sha256"],"base changed")
        dest.rename(output)
    return {"observations":expected["observations"],"database_sha256":sha(output),"sidecar_bytes":manifest["sidecar_bytes"],"base_preserved":True}

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=("export","restore"))
    p.add_argument("base",type=Path)
    p.add_argument("input",type=Path)
    p.add_argument("output",type=Path)
    p.add_argument("--manifest-sha256",help="Externally retained trusted manifest digest for restore")
    a=p.parse_args()
    if a.action=="restore":
        require(bool(a.manifest_sha256),"trusted manifest digest required")
        result=restore(a.base,a.input,a.output,a.manifest_sha256)
    else:
        result=export(a.base,a.input,a.output)
        result["manifest_sha256"]=sha(a.output/"manifest.json")
    print(json.dumps(result,sort_keys=True))
