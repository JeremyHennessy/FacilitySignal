"""Exact-release combined Care Compare extension qualification, local staging only.

Reuse the five independently qualified projectors and an immutable retained
Care Compare artifact. Never overwrite or expose a live database. The candidate
exists in a temporary directory; only aggregate evidence is published.
"""
import argparse,csv,hashlib,io,json,re,sqlite3,tempfile
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
import collect_cms as cms
import collect_registry as registry
import collect_penalties as penalties
from scripts import qualify_hospital_cost as hospital,qualify_snf_cost as snf,qualify_nursing_surveys as surveys
from scripts.verify_expanded_source_archive import load_lock
from citation_evidence import BASE_SHA
from build_combined import require,readonly,sha,validate_base,check_integrity

ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"research/coverage_status.json"
SOURCES={
 "FS-036":("penalty","nursing",15007),
 "FS-056":("hospital_cost_report","hospital",6109),
 "FS-057":("snf_cost_report","nursing",14587),
 "FS-034":("inspection_dates","nursing",148956),
 "FS-037":("survey_summary","nursing",43931),
}
TOTAL=228590

def safe_table(name):
    require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",name) is not None,"unexpected table name")
    return '"'+name+'"'

def prior_audits(ledger):
    return {"FS-036":ledger["cms_penalties_qualified_baseline"]["audit"],
            "FS-056":ledger["hospital_cost_qualified_baseline"]["audit"],
            "FS-057":ledger["snf_cost_qualified_baseline"]["audit"],
            "FS-034":ledger["nursing_survey_qualified_baselines"]["dates"]["audit"],
            "FS-037":ledger["nursing_survey_qualified_baselines"]["summary"]["audit"]}

def verify_bytes(data,pin):
    require(len(data)==pin["bytes"] and hashlib.sha256(data).hexdigest()==pin["sha256"],"pinned source bytes differ")

def download(pin):
    # Use the already verified release URL, not the publisher's current/latest
    # endpoint. No repeated API samples or full national registry retrieval.
    url=pin["url"];p=urlsplit(url)
    require(p.hostname=="data.cms.gov" and 0<pin["bytes"]<=35_000_000,"source download bound")
    client=cms.response(url) if p.path.startswith("/provider-data/") else registry.response(url,"text/csv")
    with client as res:
        require(res.geturl()==url,"pinned source redirect")
        data=res.read(pin["bytes"]+1)
    verify_bytes(data,pin)
    return data

def provider_sets(db):
    result={}
    for key,predicate in (("nursing","dataset='nursing'"),("hospital","dataset IN ('hospital','rehabilitation','long-term-hospital')")):
        found={}
        for ccn,state in db.execute("SELECT ccn,state FROM facilities WHERE "+predicate):
            found.setdefault(ccn,set()).add(state)
        result[key]=found
    return result

def move_cost_table(db,target):
    require(target in {"hospital_cost_report","snf_cost_report"},"cost namespace")
    db.execute("ALTER TABLE cost_report RENAME TO "+safe_table(target))
    db.execute("DROP INDEX cost_report_ccn")
    db.execute("CREATE INDEX "+safe_table(target+"_ccn")+" ON "+safe_table(target)+"(ccn,state)")
    db.commit()

def project_one(sid,data,pin,previous,db,providers):
    table,family,expected=SOURCES[sid]
    require(pin["input_rows"]==pin["qualified_rows"]==expected,"source count pin")
    verify_bytes(data,pin)
    if sid=="FS-036":
        result=penalties.project(data,expected,db,providers[family],previous["publisher"]["released"])
    elif sid in ("FS-056","FS-057"):
        adapter=hospital if sid=="FS-056" else snf
        header=next(csv.reader(io.StringIO(data.decode("utf-8-sig"),newline=""),strict=True),[])
        # Same bytes were independently reconciled to the version API schema
        # in the original successful qualification; do not claim a new API check.
        result=adapter.project(data,expected,previous["columns"],header,db,providers[family])
        move_cost_table(db,table)
    else:
        result=surveys.project("dates" if sid=="FS-034" else "summary",data,expected,db,providers[family])
    require(result["input_rows"]==result["stored_rows"]==expected and result["rejected_rows"]==0,"projection reconciliation")
    # Compare every stable projector output previously observed, rather than
    # just totals. Additional output fields are allowed only if they were not
    # in the earlier audit (e.g. summary footnote-state counter).
    compared=0
    for key,value in result.items():
        if key in previous and key not in {"limits","retained_row_level_records","retained_public_row_level_records"}:
            require(value==previous[key],"prior qualification mismatch: "+sid+" "+key)
            compared+=1
    require(compared>=6,"insufficient prior evidence comparison")
    require(db.execute("SELECT count(*) FROM "+safe_table(table)).fetchone()[0]==expected,"table count mismatch")
    db.execute("INSERT INTO extension_sources VALUES(?,?,?,?,?,?)",(sid,table,pin["sha256"],pin["bytes"],expected,pin["qualification_run"]))
    db.commit()
    return {"table":table,"rows":expected,"source_sha256":pin["sha256"],"original_qualification_run":pin["qualification_run"],"stable_audit_fields_compared":compared,"link_counts":result["link_counts"]}

def original_tables(db):
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}

def verify_original(db,base_path,tables):
    db.execute("ATTACH DATABASE ? AS baseline",(base_path.resolve().as_uri()+"?mode=ro",))
    result={}
    try:
        for table in sorted(tables):
            q=safe_table(table)
            n=db.execute("SELECT count(*) FROM main."+q).fetchone()[0]
            old=db.execute("SELECT count(*) FROM baseline."+q).fetchone()[0]
            require(n==old,"original table count changed")
            for a,b in (("main","baseline"),("baseline","main")):
                sql="SELECT 1 FROM (SELECT * FROM "+a+"."+q+" EXCEPT SELECT * FROM "+b+"."+q+") LIMIT 1"
                require(db.execute(sql).fetchone() is None,"original table content changed")
            result[table]=n
    finally:db.execute("DETACH DATABASE baseline")
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--cms-base",type=Path,required=True);p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    base=a.cms_base.resolve()/"facilitysignal.sqlite3"
    require(sha(base)==BASE_SHA,"retained baseline hash changed")
    validate_base(a.cms_base)
    lock=load_lock();pins={x["source_id"]:x for x in lock["expanded_sources"] if x["source_id"] in SOURCES}
    require(set(pins)==set(SOURCES),"source pin coverage")
    ledger=json.loads(LEDGER.read_text());prior=prior_audits(ledger)
    with tempfile.TemporaryDirectory(prefix="expanded-cms-") as t:
        candidate=Path(t)/"candidate.sqlite3"
        with closing(readonly(base)) as old,closing(sqlite3.connect(candidate)) as db:
            tables=original_tables(old)
            require(not (tables&({x[0] for x in SOURCES.values()}|{"extension_sources","cost_report"})),"extension namespace collision")
            old.backup(db)
            db.execute("CREATE TABLE extension_sources(source_id TEXT PRIMARY KEY,table_name TEXT UNIQUE,source_sha256 TEXT NOT NULL,source_bytes INTEGER NOT NULL,rows INTEGER NOT NULL,qualification_run INTEGER NOT NULL)")
            providers=provider_sets(db);out={}
            for sid in SOURCES:
                data=download(pins[sid])
                out[sid]=project_one(sid,data,pins[sid],prior[sid],db,providers)
                del data
                print("EXPANDED_CMS_SOURCE",sid,json.dumps(out[sid],sort_keys=True),flush=True)
            require(sum(x["rows"] for x in out.values())==TOTAL,"extension total")
            require(db.execute("SELECT count(*),sum(rows) FROM extension_sources").fetchone()==(len(SOURCES),TOTAL),"extension lineage reconciliation")
            check_integrity(db)
            db.commit()
        with closing(readonly(candidate)) as db:
            check_integrity(db)
            preserved=verify_original(db,base,tables)
            cross=surveys.compare_dates(db,db)
            require(cross=={"same_ccn_day":619069},"citation date crosscheck changed")
        require(sha(base)==BASE_SHA,"original artifact mutated")
        audit={"baseline_sha256":BASE_SHA,"baseline_scope":"nine Care Compare releases only",
               "original_table_rows":preserved,"original_primary_source_rows":preserved["facilities"]+preserved["findings"],
               "sources":out,"extension_source_rows":TOTAL,
               "combined_primary_source_rows":preserved["facilities"]+preserved["findings"]+TOTAL,
               "citation_ccn_day_crosscheck":cross,"candidate_database_sha256":sha(candidate),"candidate_database_bytes":candidate.stat().st_size,
               "original_tables_content_verified":True,"integrity_check":"passed","retained_row_level_records":0,
               "included_in_original_19_source_national_baseline":False,
               "limits":"Temporary combined Care Compare extension, not the full 19-source national database, live API, current compliance, procurement or approved commercial reuse. No source rows or candidate database retained or uploaded."}
    a.audit.parent.mkdir(parents=True,exist_ok=True)
    with a.audit.open("x") as f:json.dump(audit,f,indent=2);f.write("\n")
    print("EXPANDED_CMS_INTEGRATION_AUDIT",json.dumps(audit,sort_keys=True),flush=True)
if __name__=="__main__":main()
