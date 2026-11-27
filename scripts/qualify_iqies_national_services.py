"""Qualify the additional iQIES services against the full restored national DB.

Read-only Azure access. Temporary SQLite output; aggregate receipt only.
Never mutate archive pointers, publish source rows or write into web/.
"""
import argparse
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

import azure_national_archive as archive
import iqies_additional_services as extension
import iqies_capabilities as cap
import probe_iqies_dictionary as dictionary
from build_combined import require, readonly, sha, check_integrity
from restore_snapshot import LOCK, load_lock, fetch_missing, audit_db
from scripts import azure_verified_extension as ext

BASE_SHA = "138ad57c3719fe63895eeaff702c04b51107fe1cf6dc4daf403a554985a1f033"
BASE_RELEASE = "bootstrap-45845760984-1"
NEW_OBJECTS = {
    ("table", "iqies_additional_service_release"),
    ("table", "iqies_additional_service_observations"),
    ("index", "iqies_additional_service_field_state"),
}
STATES = {"reported_yes": 25135, "reported_no": 64526, "not_available": 4252}

def identifier(name):
    return '"' + name.replace('"', '""') + '"'

def preservation(base, candidate):
    with closing(readonly(candidate)) as db:
        check_integrity(db)
        db.execute("ATTACH DATABASE ? AS baseline", (base.resolve().as_uri()+"?mode=ro&immutable=1",))
        def objects(schema):
            return {(t,n):(table,ddl) for t,n,table,ddl in db.execute(
                "SELECT type,name,tbl_name,sql FROM "+schema+".sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
        old, new = objects("baseline"), objects("main")
        require(not (set(old)&NEW_OBJECTS) and set(new)-set(old)==NEW_OBJECTS,
                "unexpected added schema objects")
        require(all(new.get(k)==v for k,v in old.items()), "baseline schema changed")
        counts = {}
        for kind,name in sorted(old):
            if kind!="table":
                continue
            q=identifier(name)
            left=db.execute("SELECT count(*) FROM baseline."+q).fetchone()[0]
            right=db.execute("SELECT count(*) FROM main."+q).fetchone()[0]
            require(left==right,"baseline count changed: "+name)
            for a,b in (("main","baseline"),("baseline","main")):
                require(db.execute("SELECT 1 FROM (SELECT * FROM "+a+"."+q+
                    " EXCEPT SELECT * FROM "+b+"."+q+") LIMIT 1").fetchone() is None,
                    "baseline rows changed: "+name)
            # EXCEPT uses set semantics. Verify multiplicity for tables without a primary key.
            columns=list(db.execute("PRAGMA baseline.table_info("+q+")"))
            if not any(c[5] for c in columns):
                keys=",".join(identifier(c[1]) for c in columns)
                for a,b in (("main","baseline"),("baseline","main")):
                    query=lambda s: "SELECT "+keys+",count(*) FROM "+s+"."+q+" GROUP BY "+keys
                    require(db.execute("SELECT 1 FROM ("+query(a)+" EXCEPT "+query(b)+") LIMIT 1").fetchone() is None,
                            "baseline row multiplicity changed: "+name)
            counts[name]=left
        return counts

def service_checks(candidate, expected):
    with closing(readonly(candidate)) as db:
        check_integrity(db)
        states=dict(db.execute("SELECT value_state,count(*) FROM iqies_additional_service_observations GROUP BY value_state"))
        require(states==STATES, "national service state totals")
        fields={}
        for field,scope,state,n in db.execute("SELECT field,provider_scope,value_state,count(*) FROM iqies_additional_service_observations GROUP BY field,provider_scope,value_state"):
            require(field in extension.RULES and scope==extension.RULES[field][0],"service scope")
            fields.setdefault(field,{})[state]=n
        require(fields=={f:{s:n for s,n in d.items() if n} for f,d in expected.items()}, "field-state totals")
        # Exercise every field/state filter through the exact source-native join.
        for field,counts in fields.items():
            for state,n in counts.items():
                args=(field,state)
                joined=db.execute("""SELECT count(*) FROM iqies_additional_service_observations o
                    JOIN certification_records c ON c.registry=o.registry AND c.row_number=o.row_number
                    WHERE o.field=? AND o.value_state=?""",args).fetchone()[0]
                require(joined==n,"source-record filter mismatch")
        old=db.execute("SELECT count(*) FROM iqies_capability_observations").fetchone()[0]
        require(old==68604,"prior capability count")
        return {"service_states":states,"field_states":fields,"source_record_filter_checks":sum(map(len,fields.values())),
                "prior_capability_observations":old,"combined_capability_and_service_observations":old+sum(states.values())}

def run(store, root):
    national=ext.national_manifest(store)
    require(national["pointer"]["release"]==BASE_RELEASE and national["receipt"]["database_sha256"]==BASE_SHA,
            "national base changed; qualify a new base explicitly")
    base, baseline_audit=ext.restore_national(store,national,root/"base")
    item=next(s for s in load_lock(LOCK)["sources"] if s["family"]=="registry" and s["key"]=="iqies")
    raw=root/item["file"]
    fetch_missing(item,raw)
    doc=root/"iqies-dictionary.xlsx"
    dictionary.download(doc)
    require(doc.stat().st_size==cap.DICT_BYTES and sha(doc)==cap.DICT_SHA,"dictionary pin mismatch")
    result=extension.build(base,raw,doc,root/"candidate")
    candidate=root/"candidate"/"facilitysignal.sqlite3"
    require(result["verified_source_rows"]==100334 and result["observations"]==93913,"extension volume")
    counts=preservation(base,candidate)
    # Existing source-record grain is unchanged; the new derived rows are separate.
    require(audit_db(base,load_lock(LOCK))==baseline_audit["table_counts"],"base source reconciliation")
    detail=service_checks(candidate,result["field_states"])
    require(sha(base)==BASE_SHA and sha(candidate)==result["database_sha256"],"database changed during checks")
    ext.unchanged(store,national)
    return {**result,**detail,"base_release":BASE_RELEASE,"base_receipt_sha256":national["receipt_sha256"],
            "unchanged_base_table_counts":counts,"unchanged_base_tables":len(counts),
            "baseline_source_records":1904060,"national_pointer_unchanged":True,
            "private_storage_written":False,"public_promotion":False,
            "qualification_scope":"Full national archive restore plus additional service integration in temporary SQLite; no durable new snapshot or API/browser qualification."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--receipt",type=Path,required=True)
    args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists")
    archive.run_key(os.environ)
    store=archive.Azure(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="iqies-national-private-",dir=os.environ.get("RUNNER_TEMP")) as tmp:
            result=run(store,Path(tmp))
    finally:
        store.close()
    with args.receipt.open("xb") as out:
        out.write(archive.encode(result))
    print("IQIES_NATIONAL_SERVICE_QUALIFIED",json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
