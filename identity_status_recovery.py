"""National source-scoped identity candidates and iQIES status integration.

No canonical facility merge, address-derived physical property conclusion, or active
operation inference. Only exact source identifiers and documented provider scope.
"""
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date,datetime
from build_combined import require,check_integrity
import iqies_status_evidence as status
from iqies_capabilities import DICT_SHA

# QIES category 01 hospital; iQIES M1 codes from qualification 45699688960.
SCOPES={"hospital":("qies","1"),"rehabilitation":("qies","1"),
        "long-term-hospital":("qies","1"),"nursing":("iqies","20"),
        "dialysis":("iqies","7"),"home-health":("iqies","3"),"hospice":("iqies","12")}
DDL="""
CREATE TABLE IF NOT EXISTS facility_registry_candidate (
 dataset TEXT NOT NULL, ccn TEXT NOT NULL, registry TEXT NOT NULL, row_number INTEGER NOT NULL,
 candidate_state TEXT NOT NULL CHECK(candidate_state IN ('same_state','state_conflict','state_missing','provider_type_conflict')),
 address_text_agrees INTEGER CHECK(address_text_agrees IN (0,1)),
 city_text_agrees INTEGER CHECK(city_text_agrees IN (0,1)),
 zip5_agrees INTEGER CHECK(zip5_agrees IN (0,1)),
 PRIMARY KEY(dataset,ccn,registry,row_number),
 FOREIGN KEY(dataset,ccn) REFERENCES facilities(dataset,ccn),
 FOREIGN KEY(registry,row_number) REFERENCES certification_records(registry,row_number)
);
CREATE INDEX IF NOT EXISTS facility_registry_reverse ON facility_registry_candidate(registry,row_number);
"""

def norm_text(value):
    return " ".join(value.upper().split())

def agreement(a,b):
    a,b=norm_text(a),norm_text(b)
    return int(a==b) if a and b else None

def zip5(value):
    s=value.strip()
    if re.fullmatch(r"[0-9]{5}(?:-?[0-9]{4})?",s):return s[:5]
    return ""

def match_state(fstate,rstate,rawtype,expected_type):
    rawtype=rawtype.strip()
    if not re.fullmatch(r"[0-9]{1,3}",rawtype) or str(int(rawtype))!=expected_type:
        return "provider_type_conflict"
    fstate,rstate=norm_text(fstate),norm_text(rstate)
    if not fstate or not rstate:return "state_missing"
    return "same_state" if fstate==rstate else "state_conflict"

def build_candidates(db):
    db.executescript(DDL)
    result={}
    with db:
        db.execute("BEGIN IMMEDIATE")
        require(db.execute("SELECT count(*) FROM facility_registry_candidate").fetchone()[0]==0,"candidate projection already populated")
        for dataset,(registry,provider_type) in SCOPES.items():
            total=db.execute("SELECT count(*) FROM facilities WHERE dataset=?",(dataset,)).fetchone()[0]
            rows=db.execute("""SELECT f.ccn,c.row_number,f.state,c.state,c.provider_type,
                    f.address,c.address,f.city,c.city,f.zip,c.zip
                    FROM facilities f CROSS JOIN certification_records c INDEXED BY certification_id
                    ON c.registry=? AND c.provider_id=f.ccn
                    WHERE f.dataset=? AND f.ccn<>''""",(registry,dataset))
            batch=[];states=Counter()
            for ccn,n,fs,rs,rawtype,fa,ra,fc,rc,fz,rz in rows:
                state=match_state(fs,rs,rawtype,provider_type)
                states[state]+=1
                batch.append((dataset,ccn,registry,n,state,agreement(fa,ra),agreement(fc,rc),agreement(zip5(fz),zip5(rz))))
                if len(batch)>=5000:
                    db.executemany("INSERT INTO facility_registry_candidate VALUES(?,?,?,?,?,?,?,?)",batch);batch.clear()
            if batch:db.executemany("INSERT INTO facility_registry_candidate VALUES(?,?,?,?,?,?,?,?)",batch)
            actual=db.execute("SELECT count(*) FROM facility_registry_candidate WHERE dataset=?",(dataset,)).fetchone()[0]
            require(actual==sum(states.values()),"candidate row reconciliation")
            matched=db.execute("SELECT count(DISTINCT ccn) FROM facility_registry_candidate WHERE dataset=?",(dataset,)).fetchone()[0]
            strong=db.execute("SELECT count(DISTINCT ccn) FROM facility_registry_candidate WHERE dataset=? AND candidate_state='same_state'",(dataset,)).fetchone()[0]
            multi=db.execute("""SELECT count(*) FROM (SELECT ccn FROM facility_registry_candidate
                    WHERE dataset=? AND candidate_state='same_state' GROUP BY ccn HAVING count(*)>1)""",(dataset,)).fetchone()[0]
            text_agree=db.execute("""SELECT count(*) FROM facility_registry_candidate WHERE dataset=?
                    AND candidate_state='same_state' AND address_text_agrees=1 AND city_text_agrees=1 AND zip5_agrees=1""",(dataset,)).fetchone()[0]
            require(0<=strong<=matched<=total,"facility coverage reconciliation")
            result[dataset]={"facility_rows":total,"exact_identifier_candidate_pairs":actual,"pair_states":dict(states),
                    "facility_rows_with_identifier_candidate":matched,"facility_rows_without_identifier_candidate":total-matched,
                    "facility_rows_with_same_state_and_type_candidate":strong,"facility_rows_with_multiple_same_state_candidates":multi,
                    "same_state_type_and_exact_address_city_zip_text_pairs":text_agree}
        check_integrity(db)
    return result

def date_shape(raw):
    s=raw.strip()
    if not s:return "blank"
    if s.casefold()=="not available":return "not_available"
    if s.casefold()=="not applicable":return "not_applicable"
    if s.casefold() in ("null","none","n/a","na"):return "other_missing_token"
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",s):
        try:date.fromisoformat(s);return "valid_iso_date"
        except ValueError:return "invalid_iso_date"
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})?",s):
        try:datetime.fromisoformat(s.replace("Z","+00:00"));return "valid_iso_datetime"
        except ValueError:return "invalid_iso_datetime"
    if re.fullmatch(r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}",s):return "slash_date_uninterpreted"
    if re.fullmatch(r"[0-9]{8}",s):return "eight_digit_uninterpreted"
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?",s):return "numeric_uninterpreted"
    return "other_uninterpreted"

def audit_date_formats(db):
    raw=db.execute("SELECT column_mapping FROM certification_releases WHERE registry='iqies'").fetchone()
    require(raw is not None and json.loads(raw[0])["termination_date"]=="trmntn_exprtn_dt","iQIES date lineage mapping mismatch")
    counts=Counter();cross=Counter();n=0
    for value,state in db.execute("""SELECT c.termination_date,s.termination_date_state
            FROM certification_records c JOIN iqies_status_observations s
            ON c.registry=s.registry AND c.row_number=s.row_number WHERE c.registry='iqies'"""):
        shape=date_shape(value);counts[shape]+=1;cross[(shape,state)]+=1;n+=1
    require(n==100334 and sum(counts.values())==n,"date shape audit reconciliation")
    return {"rows":n,"raw_shape_counts":dict(counts),"shape_by_existing_parse_state":{k:{s:v for (shape,s),v in cross.items() if shape==k} for k in counts},
            "note":"No date values or identifiers in audit. Raw shapes remain unchanged. Audited release permits only unambiguous MDY or identical interpretations; differing interpretations remain unresolved."}

def project_status(db_path,item,path,document):
    with closing(sqlite3.connect(db_path)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        return status.project(db,path,item,document)

def finish(db_path,projection):
    require(projection["status_observations"]==projection["source_records_verified"]==100334,"status projection baseline mismatch")
    require(projection["termination_code_counts"]=={"00":74762,"01":21557,"02":146,"03":303,"04":1565,"05":725,"06":834,"07":157,"unknown":285},"termination domain baseline mismatch")
    require(projection["value_state_counts"]=={"termination_recognized":100049,"termination_unknown":285,"date_reported":15803,"date_ambiguous":9765,"date_not_available":74766,"survey_reported_no":35797,"survey_reported_yes":51409,"survey_unknown":13128,"federal_name_present":100334},"status state baseline mismatch")
    with closing(sqlite3.connect(db_path)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        row=db.execute("SELECT source_sha256,dictionary_sha256,source_rows FROM iqies_status_release").fetchone()
        require(row is not None and tuple(row)==(db.execute("SELECT source_sha256 FROM certification_releases WHERE registry='iqies'").fetchone()[0],DICT_SHA,100334),"status release lineage")
        require(db.execute("SELECT count(*) FROM iqies_status_observations").fetchone()[0]==100334,"stored status count")
        dates=audit_date_formats(db)
        require(dates["raw_shape_counts"]=={"slash_date_uninterpreted":25568,"not_available":74766},"date raw shape baseline mismatch")
        require(dates["shape_by_existing_parse_state"]=={"slash_date_uninterpreted":{"reported":15803,"ambiguous":9765},"not_available":{"not_available":74766}},"date state reconciliation")
        # Compare every projected value with the unchanged source field.
        for raw_date,projected,parse_state in db.execute("""SELECT c.termination_date,s.termination_date,s.termination_date_state
                FROM certification_records c JOIN iqies_status_observations s ON c.registry=s.registry AND c.row_number=s.row_number
                WHERE c.registry='iqies'"""):
            require((projected,parse_state)==status.parsed_date(raw_date,status.AUDITED_SLASH_RELEASE),"date projection mismatch")
        candidates=build_candidates(db)
        check_integrity(db)
    return {"status_observations":100334,"status_domain_counts":projection["termination_code_counts"],
            "status_value_state_counts":projection["value_state_counts"],"termination_date_format_audit":dates,
            "facility_registry_candidate_audit":candidates,"candidate_pairs":sum(x["exact_identifier_candidate_pairs"] for x in candidates.values()),
            "note":"Source-scoped exact CCN candidates within expected registry, provider-type and state evidence kept separate. No facility merges, physical-site resolution or active status inference."}

def profile(db,dataset,ccn):
    if dataset not in SCOPES or not re.fullmatch(r"[A-Z0-9]{6}",ccn):
        return {"status":"invalid_or_unsupported_identifier","candidates":[]}
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='facility_registry_candidate'").fetchone():
        return {"status":"not_loaded","candidates":[]}
    if not db.execute("SELECT 1 FROM facilities WHERE dataset=? AND ccn=?",(dataset,ccn)).fetchone():
        return {"status":"facility_not_found","candidates":[]}
    cur=db.execute("""SELECT registry,row_number,candidate_state,address_text_agrees,city_text_agrees,zip5_agrees
            FROM facility_registry_candidate WHERE dataset=? AND ccn=? ORDER BY registry,row_number""",(dataset,ccn))
    names=[v[0] for v in cur.description];rows=[dict(zip(names,r)) for r in cur]
    return {"status":"candidate_evidence" if rows else "no_exact_candidate","candidates":rows,
            "note":"Evidence only, not canonical identity or property resolution. Address/city/ZIP flags compare literal normalized text, not geospatial or ownership verification."}
