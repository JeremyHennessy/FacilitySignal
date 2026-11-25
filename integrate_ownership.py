"""Assemble and independently reconcile the qualified national and PECOS snapshots."""
import argparse
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from build_combined import readonly,require,check_integrity,sha
from verify_integrated import compare,PRIOR,HOSPITAL
from collect_ownership import init,audit_linkage

TABLES=("pecos_releases","pecos_enrollment_rows","pecos_org_role_rows","pecos_chow_rows")
PINS={
"hospital-enrollment":("d7ce302f73195b3ce6018291f3ee82af0ec026e51a3145bb9af41be8fbaa194e",9120,9120,0),
"hospital-owner":("4886fc907dd67d56d2c45057a13288b5e74a220f11cd6ba32b908a81728038f0",147029,22735,124294),
"hospital-chow":("a8cb5111dee64780f2c5bd9b10fdd304140848eeeee2e4b2c5012c7421533648",779,779,0),
"snf-enrollment":("21f6b282b07017f2596d9c3cb84dac3eaa100bd2ec637e0d7f03510e0f0acf89",14401,14401,0),
"snf-owner":("538b02368085b57139619c643ef5bad19c1c855cc6643e4a7eb2e6f098f46657",302718,100231,202487),
"snf-chow":("8214fe65ec7c9b291bf579bd9fcdd281fbf9bd8a593613e9db93b6f0d8bdbcb5",5340,5340,0)}

def copy_tables(db,ownership):
    init(db)
    db.execute("ATTACH DATABASE ? AS ownership",(ownership.resolve().as_uri()+"?mode=ro",))
    try:
        with db:
            for table in TABLES:
                require(db.execute("SELECT count(*) FROM main."+table).fetchone()[0]==0,"destination ownership table not empty")
                db.execute("INSERT INTO main."+table+" SELECT * FROM ownership."+table)
    finally:
        db.execute("DETACH DATABASE ownership")

def qualification(base,ownership,out):
    b=base/"facilitysignal.sqlite3"; o=ownership/"ownership.sqlite3"
    bm=json.loads((base/"integrated-audit.json").read_text())
    om=json.loads((ownership/"ownership-manifest.json").read_text())
    bh=sha(b);oh=sha(o)
    require(bh==bm["db_sha256"] and oh==om["database_sha256"],"source database hash mismatch")
    require(bm["source_records_total"]==1751454,"integrated national source count changed")
    require({x["source"]:(x["sha256"],x["input_rows"],x["stored_rows"],x["excluded_individual_rows"]) for x in om["sources"]}==PINS,"PECOS release changed since qualification")
    require(om["input_rows"]==479387 and om["stored_rows"]==152606 and om["excluded_individual_rows"]==326781,"ownership reconciliation mismatch")
    with closing(readonly(b)) as src,closing(sqlite3.connect(out)) as db:
        check_integrity(src);src.backup(db)
        copy_tables(db,o)
        check_integrity(db)
        preserved=compare(db,b,PRIOR+HOSPITAL)
        copied=compare(db,o,TABLES)
        require(copied=={"pecos_releases":6,"pecos_enrollment_rows":23521,"pecos_org_role_rows":122966,"pecos_chow_rows":6119},"copy count mismatch")
        rel=dict((x[0],tuple(x[1:])) for x in db.execute("SELECT source,sha256,expected_rows,stored_rows,excluded_individual_rows FROM pecos_releases"))
        require(rel==PINS,"database PECOS release mismatch")
        links=audit_linkage(db)
        require(all(v["unmatched_org_role_rows"]==0 for v in links.values()),"unmatched owner role")
        candidates={}
        for family,datasets in (("hospital",("hospital","rehabilitation","long-term-hospital")),("snf",("nursing",))):
            placeholders=",".join("?" for _ in datasets)
            query="""SELECT count(*) FROM pecos_enrollment_rows e WHERE e.source=? AND length(e.ccn)=6
                AND upper(e.ccn) NOT GLOB '*[^A-Z0-9]*' AND EXISTS
                (SELECT 1 FROM facilities f WHERE f.dataset IN ("""+placeholders+""") AND f.ccn=e.ccn"""
            n=db.execute("SELECT count(*) FROM pecos_enrollment_rows WHERE source=?",(family+"-enrollment",)).fetchone()[0]
            ident=db.execute(query+")",(family+"-enrollment",*datasets)).fetchone()[0]
            same=db.execute(query+" AND f.state<>'' AND f.state=upper(trim(json_extract(e.projection,'$.STATE'))))",(family+"-enrollment",*datasets)).fetchone()[0]
            candidates[family]={"enrollment_rows":n,"exact_ccn_candidates":ident,"same_state_candidates":same,"identifier_only_or_state_conflict":ident-same,"no_exact_ccn_candidate":n-ident}
    require(sha(b)==bh and sha(o)==oh,"input mutated")
    return {"prior_rows":preserved,"ownership_rows":copied,"source_records_total":bm["source_records_total"]+om["stored_rows"],"excluded_individual_rows":om["excluded_individual_rows"],"linkage_candidates":links,"care_compare_candidates":candidates,"db_sha256":sha(out),"db_bytes":out.stat().st_size,"limitations":["Local ephemeral qualification, no durable database.","Candidate matches not canonical facilities, physical properties or ownership determinations.","No row-level publication; aggregate audit only."]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base",type=Path,required=True);p.add_argument("--ownership",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();require(not out.exists(),"new output required");out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ownership-integration-",dir=out.parent) as tmp:
        stage=Path(tmp)/"ready";stage.mkdir()
        audit=qualification(a.base,a.ownership,stage/"facilitysignal.sqlite3")
        (stage/"integrated-ownership-audit.json").write_text(json.dumps(audit,indent=2)+"\n")
        os.rename(stage,out)
        print("INTEGRATED_OWNERSHIP_VERIFIED",json.dumps(audit),flush=True)

if __name__=="__main__":main()
