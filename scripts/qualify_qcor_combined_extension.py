"""Add ten pinned QCOR releases to the five-source Care Compare extension.
Temporary SQLite only; no publication of source rows or candidate database.
"""
import argparse, hashlib, json, sqlite3, tempfile, zipfile
from collections import Counter
from contextlib import closing
from pathlib import Path
import openpyxl
from scripts import qualify_expanded_cms_integration as cms
from scripts import qualify_qcor_provider as small
from scripts import qualify_qcor_expansion as expanded
from scripts.probe_qcor_icf_tag_domain import fetch_domain
from scripts.probe_qcor_hospital import request
from scripts.verify_expanded_source_archive import load_lock
from build_combined import require, readonly, sha, validate_base, check_integrity
from citation_evidence import BASE_SHA

TOTAL=628073
KEYS={**small.SOURCES,**expanded.SOURCES}
COMPARE=("input_rows","stored_rows","blank_rows","rejected_rows","row_kinds",
         "distinct_provider_keys","distinct_survey_event_keys",
         "events_with_nonmemo_tag","events_without_nonmemo_tag")

def create_tables(db):
    db.execute("""CREATE TABLE qcor_extension(
      source_id TEXT NOT NULL, ordinal INTEGER NOT NULL, provider_key TEXT NOT NULL,
      event_key TEXT NOT NULL, survey_day TEXT NOT NULL,
      row_kind TEXT NOT NULL CHECK(row_kind IN ('memo','nonmemo_tag','no_tag_reported')),
      PRIMARY KEY(source_id,ordinal)) WITHOUT ROWID""")
    db.execute("CREATE INDEX qcor_extension_event ON qcor_extension(source_id,provider_key,event_key,survey_day)")
    db.execute("""CREATE TABLE qcor_extension_sources(source_id TEXT PRIMARY KEY,
      source_sha256 TEXT NOT NULL, source_bytes INTEGER NOT NULL, rows INTEGER NOT NULL,
      qualification_run INTEGER NOT NULL)""")
    db.commit()

def exact_download(pin,path):
    url=pin["url"]
    require(url.startswith("https://qcor.cms.gov/download"),"QCOR host/path")
    require(0<pin["bytes"]<=expanded.MAX_BYTES,"workbook size bound")
    h=hashlib.sha256();size=0
    with request(url,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") as res,path.open("xb") as out:
        require(res.geturl()==url,"pinned workbook redirect")
        while chunk:=res.read(1024*1024):
            size+=len(chunk)
            require(size<=pin["bytes"],"workbook size drift")
            h.update(chunk);out.write(chunk)
    require(size==pin["bytes"] and h.hexdigest()==pin["sha256"],"workbook checksum drift")
    require(zipfile.is_zipfile(path),"not workbook")
    with zipfile.ZipFile(path) as z:
        require(len(z.infolist())<=2000 and sum(i.file_size for i in z.infolist())<=expanded.MAX_EXPANDED,"archive bound")
        require("xl/workbook.xml" in z.namelist(),"not XLSX")

def verify_domain(domain,pin):
    d=pin["required_domain"]
    digest=hashlib.sha256("\n".join(sorted(domain)).encode()).hexdigest()
    require(len(domain)==d["code_count"] and digest==d["sorted_code_sha256"],"ICF selector drift")
    return digest

def project(db,path,key,pin,prior,domain=None):
    sid=pin["source_id"]
    require(KEYS[key][0]==sid and pin["input_rows"]==pin["qualified_rows"],"source pin")
    require(path.stat().st_size==pin["bytes"] and sha(path)==pin["sha256"],"source byte drift")
    if key=="icf":
        require(domain is not None,"ICF domain missing")
        verify_domain(domain,pin)
    book=openpyxl.load_workbook(path,read_only=True,data_only=True,keep_links=False)
    try:
        require(len(book.worksheets)==1,"worksheet count")
        sheet=book.worksheets[0];sheet.reset_dimensions()
        rows=iter(sheet.iter_rows(values_only=True));header=tuple(next(rows,()))
        require(list(header)==prior["header"],"exact header changed")
        m=small.map_header(header)
        require(set(m)==set(small.ALIASES),"mapping incomplete")
        require({k:header[i] for k,i in m.items()}==prior["field_mapping"],"field mapping drift")
        total=blank=0;kinds=Counter();batch=[]
        with db:
            for ordinal,values in enumerate(rows,2):
                require(ordinal<=expanded.MAX_ROWS+1,"row limit")
                if not any(v is not None and v!="" for v in values):
                    blank+=1;continue
                total+=1
                require(len(values)<=len(header),"extra columns")
                c,e,d,k=(small.classify(values,m,key) if key in small.SOURCES else expanded.classify(values,m,key,domain))
                batch.append((sid,ordinal,c,e,d,k));kinds[k]+=1
                if len(batch)>=5000:
                    db.executemany("INSERT INTO qcor_extension VALUES(?,?,?,?,?,?)",batch);batch.clear()
            if batch:db.executemany("INSERT INTO qcor_extension VALUES(?,?,?,?,?,?)",batch)
            def scalar(sql):return db.execute(sql,(sid,)).fetchone()[0]
            n=scalar("SELECT count(*) FROM qcor_extension WHERE source_id=?")
            events=scalar("SELECT count(*) FROM (SELECT DISTINCT provider_key,event_key,survey_day FROM qcor_extension WHERE source_id=?)")
            tagged=scalar("SELECT count(*) FROM (SELECT DISTINCT provider_key,event_key,survey_day FROM qcor_extension WHERE source_id=? AND row_kind='nonmemo_tag')")
            result={"input_rows":total,"stored_rows":n,"blank_rows":blank,"rejected_rows":0,"row_kinds":dict(kinds),
                    "distinct_provider_keys":scalar("SELECT count(DISTINCT provider_key) FROM qcor_extension WHERE source_id=?"),
                    "distinct_survey_event_keys":events,"events_with_nonmemo_tag":tagged,"events_without_nonmemo_tag":events-tagged}
            require(total==n==pin["qualified_rows"]==sum(kinds.values()),"row reconciliation")
            for field in COMPARE:
                require(result[field]==prior[field],"prior audit mismatch: "+sid+" "+field)
            db.execute("INSERT INTO qcor_extension_sources VALUES(?,?,?,?,?)",(sid,pin["sha256"],pin["bytes"],n,pin["qualification_run"]))
        return {**result,"source_sha256":pin["sha256"],"original_qualification_run":pin["qualification_run"],
                "header_columns":len(header),"projected_raw_columns":len(m),
                "excluded_narrative_columns":sum(x.startswith("Statement of Deficiency Text") for x in header)}
    finally:book.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cms-base",type=Path,required=True);p.add_argument("--audit",type=Path,required=True)
    a=p.parse_args();require(not a.audit.exists(),"audit exists")
    base=a.cms_base.resolve()/"facilitysignal.sqlite3"
    require(sha(base)==BASE_SHA,"baseline hash changed");validate_base(a.cms_base)
    lock=load_lock();pins={x["source_id"]:x for x in lock["expanded_sources"]}
    ledger=json.loads(cms.LEDGER.read_text())
    previous={**ledger["qcor_provider_qualified_baselines"],**ledger["qcor_expansion_qualified_baselines"]}
    require(set(previous)==set(KEYS),"QCOR ledger coverage")
    with tempfile.TemporaryDirectory(prefix="qcor-combined-") as t:
        root=Path(t);candidate=root/"candidate.sqlite3"
        with closing(readonly(base)) as old,closing(sqlite3.connect(candidate)) as db:
            tables=cms.original_tables(old);old.backup(db)
            require(not tables&({"qcor_extension","qcor_extension_sources","extension_sources","cost_report"}|{v[0] for v in cms.SOURCES.values()}),"namespace collision")
            db.execute("CREATE TABLE extension_sources(source_id TEXT PRIMARY KEY,table_name TEXT UNIQUE,source_sha256 TEXT NOT NULL,source_bytes INTEGER NOT NULL,rows INTEGER NOT NULL,qualification_run INTEGER NOT NULL)")
            providers=cms.provider_sets(db);supplements={}
            for sid in cms.SOURCES:
                supplements[sid]=cms.project_one(sid,cms.download(pins[sid]),pins[sid],cms.prior_audits(ledger)[sid],db,providers)
            require(sum(x["rows"] for x in supplements.values())==cms.TOTAL,"CMS extension rows")
            create_tables(db);results={}
            for key in KEYS:
                sid=KEYS[key][0];pin=pins[sid];prior=previous[key]
                require(prior["run"]==pin["qualification_run"] and prior["audit"]["source"]["sha256"]==pin["sha256"],"prior lineage")
                domain=None
                if key=="icf":
                    domains,_=fetch_domain();require(len(domains)==1,"ambiguous ICF selector")
                    domain=domains[0];verify_domain(domain,pin)
                path=root/pin["file"];exact_download(pin,path)
                results[sid]=project(db,path,key,pin,prior["audit"],domain)
                path.unlink()
                print("QCOR_COMBINED_SOURCE",sid,json.dumps(results[sid],sort_keys=True),flush=True)
            require(db.execute("SELECT count(*),sum(rows) FROM qcor_extension_sources").fetchone()==(10,TOTAL),"QCOR lineage")
            require(db.execute("SELECT count(*) FROM qcor_extension").fetchone()[0]==TOTAL,"QCOR count")
            require(sum(x["stored_rows"] for x in results.values())==TOTAL,"QCOR total")
            check_integrity(db);db.commit()
        with closing(readonly(candidate)) as db:
            check_integrity(db);preserved=cms.verify_original(db,base,tables)
            require(cms.surveys.compare_dates(db,db)=={"same_ccn_day":619069},"citation crosscheck")
            require(db.execute("SELECT count(*),sum(rows) FROM extension_sources").fetchone()==(5,cms.TOTAL),"CMS lineage")
        require(sha(base)==BASE_SHA,"baseline modified")
        original=preserved["facilities"]+preserved["findings"]
        audit={"original_table_rows":preserved,"baseline_sha256":BASE_SHA,"original_primary_source_rows":original,
               "original_tables_content_verified":True,"cms_extension_sources":supplements,"cms_extension_rows":cms.TOTAL,
               "qcor_sources":results,"qcor_extension_rows":TOTAL,"combined_primary_source_rows":original+cms.TOTAL+TOTAL,
               "candidate_database_bytes":candidate.stat().st_size,"candidate_database_sha256":sha(candidate),
               "integrity_check":"passed","retained_row_level_records":0,"reuse_review":"pending",
               "limits":"Temporary nine-release Care Compare baseline plus fifteen qualified extensions, not the full national 19-release baseline. Source-scoped event/provider keys, not canonical site links, current compliance, or purchasing intent. No names, addresses, narratives, or tag values stored in QCOR projection; no candidate or row-level records uploaded."}
    a.audit.parent.mkdir(parents=True,exist_ok=True)
    with a.audit.open("x") as f:json.dump(audit,f,indent=2);f.write("\n")
    print("QCOR_COMBINED_AUDIT",json.dumps(audit,sort_keys=True),flush=True)

if __name__=="__main__":main()
