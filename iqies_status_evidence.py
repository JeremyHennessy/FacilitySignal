"""Preserve iQIES program termination, federal certification and survey status separately.

The official M2 code list is interpreted only for the termination-code field.
Do not infer current operation or merge sites; no public provider-level outputs.
"""
import argparse,csv,hashlib,json,os,re,sqlite3,tempfile
from collections import Counter
from contextlib import closing
from datetime import date,datetime,timezone
from pathlib import Path
import openpyxl
import facilitysignal as fs
import collect_registry as registry
import probe_iqies_dictionary as dictionary
import iqies_capabilities as iq
from build_combined import require,check_integrity,sha,readonly
from restore_snapshot import LOCK,load_lock,materialize,verify_raw
from probe_pos_fields import INVENTORY

FIELDS={"pgm_trmntn_cd":(102,"Termination Code","M2"),"fed_crtfctn_stus_id":(100,"Federal Certification Status ID",None),
"fed_crtfctn_stus_name":(101,"Federal Certification Status Name",None),
"cmplnc_stus_cd":(27,"Compliance Status Code",None),"trmntn_exprtn_dt":(14,"Termination or Expiration Date",None)}
DDL="""
CREATE TABLE IF NOT EXISTS iqies_status_release(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 source_sha256 TEXT NOT NULL,dictionary_sha256 TEXT NOT NULL,source_period TEXT NOT NULL,
 dictionary_url TEXT NOT NULL,source_rows INTEGER NOT NULL,imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS iqies_termination_dictionary(
 code TEXT PRIMARY KEY,label TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS iqies_status_observations(
 registry TEXT NOT NULL CHECK(registry='iqies'),row_number INTEGER NOT NULL,
 termination_code TEXT,termination_value_state TEXT NOT NULL CHECK(termination_value_state IN ('recognized','blank','unknown')),
 federal_status_id TEXT,federal_status_name TEXT,
 survey_compliance_raw TEXT,survey_compliance_value_state TEXT NOT NULL CHECK(survey_compliance_value_state IN ('reported_yes','reported_no','blank','unknown')),
 termination_date TEXT,termination_date_state TEXT NOT NULL CHECK(termination_date_state IN ('reported','blank','unknown')),
 PRIMARY KEY(registry,row_number),
 FOREIGN KEY(registry,row_number) REFERENCES certification_records(registry,row_number),
 FOREIGN KEY(termination_code) REFERENCES iqies_termination_dictionary(code),
 CHECK((termination_code IS NOT NULL)=(termination_value_state='recognized')),
 CHECK((termination_date IS NOT NULL)=(termination_date_state='reported'))
);
CREATE INDEX IF NOT EXISTS iqies_status_code ON iqies_status_observations(termination_code,termination_date_state);
"""

def code_token(raw):
    s=str(raw).strip()
    return s.zfill(2) if re.fullmatch(r"[0-9]{1,2}",s) else None

def parse_domain(rows):
    out={}
    for row in rows:
        if not row or not any(v is not None for v in row):continue
        require(len(row)>=2 and row[0] is not None and row[1] is not None,"M2 incomplete row")
        code=code_token(row[0]);label=str(row[1]).strip()
        require(code is not None and label and code not in out,"M2 invalid or duplicate code")
        out[code]=label
    require(len(out)==22 and out.get("00")=="Active","M2 domain mismatch")
    return out

def load_dictionary(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size==iq.DICT_BYTES and sha(path)==iq.DICT_SHA,"dictionary release changed")
    book=openpyxl.load_workbook(path,read_only=True,data_only=True,keep_links=False)
    try:
        sheet=book["POS Data Dictionary"];sheet.reset_dimensions()
        matched=set()
        for n,row in enumerate(sheet.iter_rows(values_only=True),1):
            row=tuple(row)+(None,)*max(0,6-len(row))
            if row[0] in FIELDS:
                key=row[0];ordinal,label,mapping=FIELDS[key]
                require(key not in matched and (n,row[2],row[5])==(ordinal,label,mapping),"field dictionary mismatch: "+key)
                matched.add(key)
        require(matched==set(FIELDS),"missing status field")
        m=book["M2"];m.reset_dimensions();rows=iter(m.iter_rows(values_only=True))
        require(tuple(next(rows))[:2]==("ID","Value"),"M2 header mismatch")
        return parse_domain(rows)
    finally:book.close()

def termination(raw,domain):
    if not raw.strip():return None,"blank"
    token=code_token(raw)
    return (token,"recognized") if token in domain else (None,"unknown")

def survey(raw):
    return {"yes":"reported_yes","no":"reported_no","":"blank"}.get(raw.strip().casefold(),"unknown")

def parsed_date(raw):
    s=raw.strip()
    if not s:return None,"blank"
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",s):
        try:return date.fromisoformat(s).isoformat(),"reported"
        except ValueError:pass
    return None,"unknown"

def project(db,source,item,dictionary_path):
    domain=load_dictionary(dictionary_path);verify_raw(source,item)
    rel=db.execute("SELECT source_sha256,row_count,period FROM certification_releases WHERE registry='iqies'").fetchone()
    require(rel is not None and tuple(rel)==(item["sha256"],item["stored_rows"],item["release"]),"registry release mismatch")
    headers=[x["field"] for x in json.loads(INVENTORY.read_text())["registries"]["iqies"]["fields"]]
    db.executescript(DDL);codes=Counter();states=Counter();cross=Counter();fed=Counter();n=0
    with db,registry.open_csv(source,item["metadata"]["zipped"],registry.source_encoding(source,item["metadata"]["zipped"])) as f:
        db.execute("BEGIN IMMEDIATE")
        require(db.execute("SELECT count(*) FROM iqies_status_release").fetchone()[0]==0,"status release exists")
        db.execute("INSERT INTO iqies_status_release VALUES(1,?,?,?,?,?,?)",(item["sha256"],iq.DICT_SHA,item["release"],dictionary.URL,item["stored_rows"],datetime.now(timezone.utc).isoformat()))
        db.executemany("INSERT INTO iqies_termination_dictionary VALUES(?,?)",sorted(domain.items()))
        reader=csv.DictReader(f)
        require(reader.fieldnames==headers and set(FIELDS).issubset(reader.fieldnames),"status source schema drift")
        refs=db.execute("SELECT row_number,row_sha256,provider_id,provider_type FROM certification_records WHERE registry='iqies' ORDER BY row_number")
        batch=[]
        for n,(row,ref) in enumerate(zip(reader,refs,strict=True),1):
            require(None not in row and all(v is not None for v in row.values()),"malformed source row")
            digest=hashlib.sha256(json.dumps(list(row.values()),ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
            require((n,digest,row["prvdr_num"].strip(),row["prvdr_type_id"].strip())==tuple(ref),"registry lineage mismatch")
            code,term_state=termination(row["pgm_trmntn_cd"],domain)
            status_id=row["fed_crtfctn_stus_id"].strip() or None
            status_name=row["fed_crtfctn_stus_name"].strip() or None
            survey_raw=row["cmplnc_stus_cd"].strip() or None
            compliance=survey(survey_raw or "")
            dt,dt_state=parsed_date(row["trmntn_exprtn_dt"])
            states["termination_"+term_state]+=1;states["date_"+dt_state]+=1;states["survey_"+compliance]+=1
            codes[code if code is not None else term_state]+=1
            cross[(code if code is not None else term_state,dt_state)]+=1
            # Report only bounded numeric ID domains; arbitrary source strings remain local.
            id_bucket=status_id if status_id and re.fullmatch(r"[0-9]{1,4}",status_id) else ("blank" if status_id is None else "unknown")
            fed[id_bucket]+=1
            states["federal_name_present" if status_name is not None else "federal_name_blank"]+=1
            batch.append(("iqies",n,code,term_state,status_id,status_name,survey_raw,compliance,dt,dt_state))
            if len(batch)>=5000:
                db.executemany("INSERT INTO iqies_status_observations VALUES(?,?,?,?,?,?,?,?,?,?)",batch);batch.clear()
        if batch:db.executemany("INSERT INTO iqies_status_observations VALUES(?,?,?,?,?,?,?,?,?,?)",batch)
        require(n==item["input_rows"]==db.execute("SELECT count(*) FROM iqies_status_observations").fetchone()[0],"status row reconciliation")
        require(sum(codes.values())==sum(cross.values())==sum(fed.values())==n,"status audit reconciliation")
        for prefix in ("termination_","date_","survey_","federal_name_"):
            require(sum(v for k,v in states.items() if k.startswith(prefix))==n,"status state reconciliation: "+prefix)
        check_integrity(db)
    verify_raw(source,item)
    return {"source_records_verified":n,"status_observations":n,"dictionary_codes":domain,"termination_code_counts":dict(codes),
            "termination_code_by_date_state":{k:{s:v for (c,s),v in cross.items() if c==k} for k in codes},
            "value_state_counts":dict(states),"federal_status_id_counts":dict(fed),
            "federal_status_distinct_nonblank_names":db.execute("SELECT count(DISTINCT federal_status_name) FROM iqies_status_observations").fetchone()[0],
            "limitations":["M2 'Active' describes program termination code only; not a verified current operating facility or even a canonical active certificate.","Federal status ID/name are source-native; no authoritative crosswalk claimed. Survey compliance refers to certification survey, not present compliance.","Date state is syntactic validity only; no timeline or physical-site inference. Unknown and blank remain distinct.","Local qualification, aggregate-only evidence; derived records not additional provider records."]}

def profile(db,provider_id):
    if not re.fullmatch(r"[A-Za-z0-9]{6,10}",provider_id):return {"status":"invalid_identifier","rows":[]}
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='iqies_status_release'").fetchone():return {"status":"not_loaded","rows":[]}
    rel=db.execute("SELECT source_sha256,dictionary_sha256,source_period,dictionary_url FROM iqies_status_release").fetchone()
    if not rel:return {"status":"not_loaded","rows":[]}
    sql="""SELECT s.row_number,s.termination_code,d.label AS termination_code_label,s.termination_value_state,
        s.federal_status_id,s.federal_status_name,s.survey_compliance_raw,s.survey_compliance_value_state,s.termination_date,s.termination_date_state
        FROM certification_records c JOIN iqies_status_observations s ON s.registry=c.registry AND s.row_number=c.row_number
        LEFT JOIN iqies_termination_dictionary d ON d.code=s.termination_code
        WHERE c.registry='iqies' AND c.provider_id=? ORDER BY s.row_number"""
    cur=db.execute(sql,(provider_id,));names=[x[0] for x in cur.description];rows=[dict(zip(names,row)) for row in cur]
    return {"status":"source_observations" if rows else "no_qualified_observations","rows":rows,
            "release":dict(zip(("source_sha256","dictionary_sha256","source_period","dictionary_url"),rel)),
            "note":"Source-native program termination status, federal certification status, certification-survey compliance, and date are separate evidence. No current operation inferred."}

def build(output,raw_dir,dictionary_path,base_db,allow_download):
    item=next(s for s in load_lock(LOCK)["sources"] if s["family"]=="registry" and s["key"]=="iqies")
    output=output.resolve();require(not output.exists(),"output must be new");output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".iqies-status-",dir=output.parent) as tmp:
        stage=Path(tmp);raw=stage/"raw";raw.mkdir();ready=stage/"ready";ready.mkdir()
        source=materialize(item,raw_dir,raw,allow_download)
        if dictionary_path is None:
            require(allow_download,"dictionary path required without explicit download")
            dictionary_path=raw/"dictionary.xlsx";dictionary.download(dictionary_path)
        dbpath=ready/"facilitysignal.sqlite3";before=sha(base_db) if base_db else None
        if base_db:
            with closing(readonly(base_db)) as src,closing(sqlite3.connect(dbpath)) as dst:check_integrity(src);src.backup(dst)
        else:
            fs.init(dbpath);registry.import_registry(dbpath,item["metadata"],source,item["sha256"],item["input_rows"])
        with closing(sqlite3.connect(dbpath)) as db:
            db.execute("PRAGMA foreign_keys=ON");audit=project(db,source,item,dictionary_path)
        if base_db:require(sha(base_db)==before,"baseline mutated")
        audit.update({"source_sha256":item["sha256"],"source_period":item["release"],"dictionary_sha256":iq.DICT_SHA,"database_sha256":sha(dbpath),"database_bytes":dbpath.stat().st_size,"base_database_sha256":before})
        (ready/"iqies-status-audit.json").write_text(json.dumps(audit,indent=2)+"\n")
        os.rename(ready,output);print("IQIES_STATUS_VERIFIED",json.dumps(audit),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);p.add_argument("--raw-dir",type=Path);p.add_argument("--dictionary",type=Path);p.add_argument("--base-db",type=Path);p.add_argument("--download",action="store_true")
    a=p.parse_args();build(a.output,a.raw_dir,a.dictionary,a.base_db,a.download)
