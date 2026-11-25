"""Qualified source-scoped iQIES ASC and ESRD capability observations.

Local development only; no physical asset, procurement or active-status inference.
Uses the same pinned source bytes and full row hashes as certification_records.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
import openpyxl
import facilitysignal as fs
import collect_registry as registry
import probe_iqies_dictionary as dictionary
from build_combined import require,check_integrity,readonly,sha
from restore_snapshot import LOCK,load_lock,materialize,verify_raw
from probe_pos_fields import INVENTORY

DICT_SHA="bd68d76dc72ee5c3b3249c459644ff2ed90c8e8cf6e182b76742ec53164c0594"
DICT_BYTES=40305
# Exact dictionary fields, provider applicability, data interpretation and sheet rows
# reviewed from run 45696260706. Do not add codes or guess unsupported spellings.
RULES={
"oprtg_room_cnt":("ASC","count","Operating Room Count",46),
"procedure_room_cnt":("ASC","count","Procedure Room Count",47),
"dntl_srgry_sw":("ASC","boolean","Surgical Specialty: Dental Indicator",42),
"endscpy_srgry_sw":("ASC","boolean","Surgical Specialty: Endoscopy Indicator",43),
"dlys_stn_cnt":("ESRD","count","Number of Approved In-Center Dialysis Stations",142),
"hmdlys_srvc_sw":("ESRD","boolean","Is Current In-Center Hemodialysis",136),
"prtnl_dlys_srvc_sw":("ESRD","boolean","Is Current In-Center Peritoneal Dialysis",138),
"home_trng_sprt_only_srvc_sw":("ESRD","boolean","Is Onsite Home Training Provided",133)
}
TYPE_LABELS={
"ASC":{"ambulatory surgical center","ambulatory surgery center","ambulatory surgical centers","ambulatory surgical center asc","ambulatory surgery center asc","asc"},
"ESRD":{"end stage renal disease","end stage renal disease facility","end stage renal disease facilities","end stage renal disease esrd","end stage renal disease facility esrd","esrd"}
}
DDL="""
CREATE TABLE IF NOT EXISTS iqies_capability_release (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 source_sha256 TEXT NOT NULL, dictionary_sha256 TEXT NOT NULL,
 source_period TEXT NOT NULL, dictionary_url TEXT NOT NULL,
 source_rows INTEGER NOT NULL, imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS iqies_capability_observations (
 registry TEXT NOT NULL CHECK(registry='iqies'),
 row_number INTEGER NOT NULL,
 field TEXT NOT NULL,
 provider_scope TEXT NOT NULL CHECK(provider_scope IN ('ASC','ESRD')),
 value_state TEXT NOT NULL CHECK(value_state IN ('reported_count','reported_yes','reported_no','not_available','not_applicable_conflict','blank','unrecognized')),
 count_value INTEGER CHECK(count_value>=0),
 PRIMARY KEY(registry,row_number,field),
 FOREIGN KEY(registry,row_number) REFERENCES certification_records(registry,row_number),
 CHECK((value_state='reported_count' AND count_value IS NOT NULL) OR (value_state<>'reported_count' AND count_value IS NULL))
);
CREATE INDEX IF NOT EXISTS iqies_capability_field_state ON iqies_capability_observations(field,value_state);
"""

def normalize_label(value):
    return " ".join(re.sub(r"[^a-z0-9]+"," ",str(value).casefold()).split())

def normalize_code(value):
    s=str(value).strip()
    return str(int(s)) if re.fullmatch(r"[0-9]{1,9}",s) else None

def scope_mapping(mapping_rows):
    all_codes={}; resolved={}
    for code,label,*_ in mapping_rows:
        if code is None and label is None:continue
        k=normalize_code(code)
        require(k is not None and label is not None and k not in all_codes,"M1 provider code ambiguous")
        all_codes[k]=str(label).strip()
        normalized=normalize_label(label)
        for scope,aliases in TYPE_LABELS.items():
            if normalized in aliases:
                require(scope not in resolved.values(),"multiple dictionary provider types for "+scope)
                resolved[k]=scope
    require(set(resolved.values())==set(TYPE_LABELS),"dictionary provider type labels require review")
    return all_codes,resolved

def load_dictionary(path):
    require(path.stat().st_size==DICT_BYTES and sha(path)==DICT_SHA,"dictionary release changed")
    book=openpyxl.load_workbook(path,read_only=True,data_only=True,keep_links=False)
    try:
        sheet=book["POS Data Dictionary"];sheet.reset_dimensions()
        observed={}
        for n,row in enumerate(sheet.iter_rows(values_only=True),1):
            row=tuple(row)+(None,)*max(0,6-len(row))
            if row[0] in RULES:
                field=row[0];scope,kind,label,expected_row=RULES[field]
                require(field not in observed and n==expected_row and row[2]==label and row[4]==scope,"dictionary field/applicability mismatch: "+field)
                if kind=="boolean":
                    require(row[1]=="Yes/No/Not Applicable/Not Available","dictionary boolean domain mismatch")
                else:
                    require(row[1] in ("string","INT/Not Applicable/Not Available"),"dictionary count format mismatch")
                require(not row[5],"unexpected mapping for selected field")
                observed[field]={"dictionary_row":n,"label":label,"scope":scope,"kind":kind}
        require(set(observed)==set(RULES),"missing reviewed field")
        m=book["M1"];m.reset_dimensions()
        rows=iter(m.iter_rows(values_only=True))
        require(tuple(next(rows))[:2]==("ID","Value"),"M1 header mismatch")
        all_codes,scopes=scope_mapping(rows)
        return observed,all_codes,scopes
    finally:
        book.close()

def normalize_value(value,kind):
    s=value.strip().casefold()
    if not s:return "blank",None
    if s=="not available":return "not_available",None
    if s=="not applicable":return "not_applicable_conflict",None
    if kind=="boolean":
        if s=="yes":return "reported_yes",None
        if s=="no":return "reported_no",None
    elif kind=="count" and re.fullmatch(r"[0-9]{1,12}",s):
        return "reported_count",int(s)
    return "unrecognized",None

def project(db,path,item,dictionary_path):
    rules,codes,scopes=load_dictionary(dictionary_path)
    verify_raw(path,item)
    rel=db.execute("SELECT source_sha256,row_count,period FROM certification_releases WHERE registry='iqies'").fetchone()
    require(rel is not None and tuple(rel)==(item["sha256"],item["stored_rows"],item["release"]),"registry release mismatch")
    require(db.execute("SELECT count(*) FROM certification_records WHERE registry='iqies'").fetchone()[0]==item["stored_rows"],"registry row count mismatch")
    expected_headers=[x["field"] for x in json.loads(INVENTORY.read_text())["registries"]["iqies"]["fields"]]
    db.executescript(DDL)
    stats=Counter();states=Counter();scope_counts=Counter();field_counts=Counter();observed_values=Counter()
    n=0
    with db,registry.open_csv(path,item["metadata"]["zipped"],registry.source_encoding(path,item["metadata"]["zipped"])) as source:
        db.execute("BEGIN IMMEDIATE")
        require(db.execute("SELECT count(*) FROM iqies_capability_release").fetchone()[0]==0,"existing capability release")
        db.execute("INSERT INTO iqies_capability_release VALUES(1,?,?,?,?,?,?)",(item["sha256"],DICT_SHA,item["release"],dictionary.URL,item["stored_rows"],datetime.now(timezone.utc).isoformat()))
        reader=csv.DictReader(source)
        require(reader.fieldnames==expected_headers,"pinned CSV header mismatch")
        reference=db.execute("SELECT row_number,row_sha256,provider_id,provider_type FROM certification_records WHERE registry='iqies' ORDER BY row_number")
        batch=[]
        for n,(row,ref) in enumerate(zip(reader,reference,strict=True),1):
            require(None not in row and all(v is not None for v in row.values()),"malformed CSV row")
            row_hash=hashlib.sha256(json.dumps(list(row.values()),ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
            require((n,row_hash,row["prvdr_num"].strip(),row["prvdr_type_id"].strip())==tuple(ref),"registry row lineage mismatch")
            code=normalize_code(row["prvdr_type_id"]);scope=scopes.get(code)
            if code not in codes:stats["unrecognized_provider_type_rows"]+=1
            if scope:scope_counts[scope]+=1
            for field,(expected_scope,kind,label,drow) in RULES.items():
                raw=row[field]
                if scope!=expected_scope:
                    if raw.strip().casefold() not in ("","not applicable"):
                        stats["out_of_scope_nonblank_"+field]+=1
                    continue
                state,value=normalize_value(raw,kind)
                states[(field,state)]+=1;field_counts[field]+=1
                if value is not None:observed_values[field]+=value
                batch.append(("iqies",n,field,scope,state,value))
                if len(batch)>=5000:
                    db.executemany("INSERT INTO iqies_capability_observations VALUES(?,?,?,?,?,?)",batch);batch.clear()
        if batch:db.executemany("INSERT INTO iqies_capability_observations VALUES(?,?,?,?,?,?)",batch)
        require(n==item["input_rows"],"input count mismatch")
        require(set(scope_counts)==set(TYPE_LABELS),"scope missing in source")
        expected=sum(scope_counts[s] for s,_,_,_ in RULES.values())
        actual=db.execute("SELECT count(*) FROM iqies_capability_observations").fetchone()[0]
        require(actual==expected==sum(states.values()),"capability observation reconciliation")
        require(dict(db.execute("SELECT field,count(*) FROM iqies_capability_observations GROUP BY field"))==dict(field_counts),"field reconciliation")
        check_integrity(db)
    verify_raw(path,item)
    return {"source_records_verified":n,"provider_scope_rows":dict(scope_counts),"capability_observations":actual,
            "field_states":{f:{s:count for (k,s),count in states.items() if k==f} for f in RULES},
            "count_value_totals":dict(observed_values),"quality_flags":dict(stats),
            "provider_type_dictionary":codes,"reviewed_scope_codes":scopes,"reviewed_fields":rules,
            "limitations":["Observations on source registry rows, not distinct facilities or documented installed equipment.","Source period Q3 2026; no current operating status, procurement or sales opportunity inferred.","Nonapplicable scope values excluded from interpretation; anomalies counted. Unknown is not zero. Local qualification only; no public row-level redistribution."]}

def profile(db,provider_id):
    if not re.fullmatch(r"[A-Za-z0-9]{6,10}",provider_id):
        return {"status":"invalid_identifier","rows":[]}
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='iqies_capability_release'").fetchone():
        return {"status":"not_loaded","rows":[]}
    release=db.execute("SELECT source_sha256,dictionary_sha256,source_period,dictionary_url FROM iqies_capability_release").fetchone()
    if not release:return {"status":"not_loaded","rows":[]}
    # Exact source identifier only; no inferred Care Compare or physical-site link.
    result=[]
    for row_number,field,scope,state,value in db.execute("""SELECT o.row_number,o.field,o.provider_scope,o.value_state,o.count_value
            FROM certification_records c JOIN iqies_capability_observations o
            ON o.registry=c.registry AND o.row_number=c.row_number
            WHERE c.registry='iqies' AND c.provider_id=? ORDER BY o.row_number,o.field""",(provider_id,)):
        result.append({"row_number":row_number,"field":field,"label":RULES[field][2],"provider_scope":scope,"value_state":state,"count_value":value,"dictionary_row":RULES[field][3]})
    return {"status":"source_observations" if result else "no_qualified_observations","rows":result,
            "release":{"source_sha256":release[0],"dictionary_sha256":release[1],"source_period":release[2],"dictionary_url":release[3]},
            "note":"Source-scoped observations; no physical asset ownership, current operation or purchase intent inferred."}

def build(output,raw_dir,dictionary_path,base_db,allow_download):
    item=next(s for s in load_lock(LOCK)["sources"] if s["family"]=="registry" and s["key"]=="iqies")
    output=output.resolve();require(not output.exists(),"output must be new");output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".iqies-capabilities-",dir=output.parent) as tmp:
        stage=Path(tmp);raw=stage/"raw";raw.mkdir();ready=stage/"ready";ready.mkdir()
        path=materialize(item,raw_dir,raw,allow_download)
        if dictionary_path is None:
            require(allow_download,"dictionary path required without explicit download")
            dictionary_path=raw/"dictionary.xlsx";dictionary.download(dictionary_path)
        db_path=ready/"facilitysignal.sqlite3"
        old_hash=sha(base_db) if base_db else None
        if base_db:
            with closing(readonly(base_db)) as src,closing(sqlite3.connect(db_path)) as dst:
                check_integrity(src);src.backup(dst)
        else:
            fs.init(db_path)
            registry.import_registry(db_path,item["metadata"],path,item["sha256"],item["input_rows"])
        with closing(sqlite3.connect(db_path)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            audit=project(db,path,item,dictionary_path)
        if base_db:
            require(sha(base_db)==old_hash,"baseline mutated")
        audit.update({"source_sha256":item["sha256"],"dictionary_sha256":DICT_SHA,"database_sha256":sha(db_path),"database_bytes":db_path.stat().st_size,"base_database_sha256":old_hash,"source_period":item["release"]})
        (ready/"iqies-capability-audit.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        os.rename(ready,output)
        print("IQIES_CAPABILITIES_VERIFIED",json.dumps(audit),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True);p.add_argument("--raw-dir",type=Path);p.add_argument("--dictionary",type=Path)
    p.add_argument("--base-db",type=Path);p.add_argument("--download",action="store_true")
    a=p.parse_args();build(a.output,a.raw_dir,a.dictionary,a.base_db,a.download)
if __name__=="__main__":main()
