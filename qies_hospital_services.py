"""QIES hospital service evidence, using the publisher-linked legacy record layout.

Keep historical reference semantics explicitly provisional. Only aggregate audit
is published. No current asset, physical site, contract or purchase inference.
"""
import argparse
import csv
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
import facilitysignal as fs
import collect_registry as registry
from build_combined import require,check_integrity,sha,readonly
from restore_snapshot import LOCK,load_lock,materialize,verify_raw
from probe_pos_fields import INVENTORY

LAYOUT_URL="https://data.cms.gov/sites/default/files/2023-07/0ca58d5d-7914-4532-b22d-41741d3e6151/P.QWB.POSQ.OTHER.LAYOUT.MAR23.pdf"
LAYOUT_DATE="2023-04-02"
# Scope and field/domain reviewed in the Hospital category 01 portion of the
# catalog-linked layout. Keep mappings provisional pending current-version review.
FIELDS={
"CT_SCAN_SRVC_CD":"CT services",
"MGNTC_RSNC_IMG_SRVC_CD":"MRI services",
"PET_SCAN_SRVC_CD":"PET services",
"NUCLR_MDCN_SRVC_CD":"Nuclear medicine services",
"DNTL_SRVC_CD":"Dental services",
"OPRTG_ROOM_SRVC_CD":"Operating room services",
"DGNSTC_RDLGY_SRVC_CD":"Diagnostic radiology services",
"DTRY_SRVC_CD":"Dietary services",
"DCTD_ER_SRVC_CD":"Emergency department services",
"ICU_SRVC_CD":"Medical-surgical ICU services",
"NEONTL_ICU_SRVC_CD":"Neonatal ICU services",
"OPEN_HRT_SRGRY_SRVC_CD":"Cardiothoracic surgery services"
}
# Historical published domain, not a current-version claim.
REFERENCE={"0":"not_provided","1":"staff","2":"arrangement","3":"staff_and_arrangement"}
DDL="""
CREATE TABLE IF NOT EXISTS qies_hospital_service_release(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 source_sha256 TEXT NOT NULL, layout_sha256 TEXT NOT NULL,
 source_period TEXT NOT NULL, layout_url TEXT NOT NULL,
 layout_date TEXT NOT NULL, source_rows INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS qies_hospital_service_observations(
 registry TEXT NOT NULL CHECK(registry='qies'), row_number INTEGER NOT NULL,
 field TEXT NOT NULL, value_state TEXT NOT NULL CHECK(value_state IN
 ('historical_domain_code','blank','not_available','not_applicable','unrecognized')),
 code TEXT CHECK(code IN ('0','1','2','3')),
 PRIMARY KEY(registry,row_number,field),
 FOREIGN KEY(registry,row_number) REFERENCES certification_records(registry,row_number),
 CHECK((value_state='historical_domain_code' AND code IS NOT NULL) OR
       (value_state<>'historical_domain_code' AND code IS NULL))
);
CREATE INDEX IF NOT EXISTS qies_hospital_service_field ON qies_hospital_service_observations(field,value_state,code);
"""

def is_hospital(category):
    # The dictionary documents hospital category 01. Preserve original source
    # representation; only canonical decimal equivalents are accepted.
    return category.strip() in ("01","1")

def classify(value):
    v=value.strip()
    if not v:return "blank",None
    if v.casefold()=="not available":return "not_available",None
    if v.casefold()=="not applicable":return "not_applicable",None
    if v in REFERENCE:return "historical_domain_code",v
    return "unrecognized",None

def dictionary_evidence(path):
    catalog=registry.get_json(registry.CATALOG)
    found=[x for x in catalog["dataset"] if x.get("title")==registry.TITLES["qies"]]
    require(len(found)==1 and found[0].get("describedBy")==LAYOUT_URL,"publisher dictionary reference changed")
    h=hashlib.sha256();n=0
    with registry.response(LAYOUT_URL,"application/pdf") as src,path.open("xb") as dst:
        require(src.geturl()==LAYOUT_URL,"layout redirect changed")
        first=src.read(5)
        require(first==b"%PDF-","layout not PDF")
        dst.write(first);h.update(first);n=len(first)
        while chunk:=src.read(1024*1024):
            n+=len(chunk);require(n<=30_000_000,"layout size limit")
            h.update(chunk);dst.write(chunk)
    return {"url":LAYOUT_URL,"sha256":h.hexdigest(),"bytes":n,"document_date":LAYOUT_DATE,"catalog_reference_verified":True}

def project(db,source,item,layout):
    verify_raw(source,item)
    rel=db.execute("SELECT source_sha256,row_count,period FROM certification_releases WHERE registry='qies'").fetchone()
    require(rel is not None and tuple(rel)==(item["sha256"],item["stored_rows"],item["release"]),"QIES release mismatch")
    expected_headers=[x["field"] for x in json.loads(INVENTORY.read_text())["registries"]["qies"]["fields"]]
    categories=Counter();states=Counter();other=Counter();n=hosp=0
    db.executescript(DDL)
    with db,registry.open_csv(source,item["metadata"]["zipped"],registry.source_encoding(source,item["metadata"]["zipped"])) as stream:
        db.execute("BEGIN IMMEDIATE")
        require(db.execute("SELECT count(*) FROM qies_hospital_service_release").fetchone()[0]==0,"existing service release")
        db.execute("INSERT INTO qies_hospital_service_release VALUES(1,?,?,?,?,?,?)",(item["sha256"],layout["sha256"],item["release"],LAYOUT_URL,LAYOUT_DATE,item["stored_rows"]))
        reader=csv.DictReader(stream)
        require(reader.fieldnames==expected_headers,"QIES header drift")
        require(set(FIELDS).issubset(reader.fieldnames),"reviewed fields absent")
        refs=db.execute("SELECT row_number,row_sha256,provider_id,provider_type FROM certification_records WHERE registry='qies' ORDER BY row_number")
        batch=[]
        for n,(row,ref) in enumerate(zip(reader,refs,strict=True),1):
            require(None not in row and all(v is not None for v in row.values()),"malformed source record")
            digest=hashlib.sha256(json.dumps(list(row.values()),ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
            cat=row["PRVDR_CTGRY_CD"].strip()
            require((n,digest,row["PRVDR_NUM"].strip(),cat)==tuple(ref),"registry lineage mismatch")
            # Category itself is a documented source code, not a person or address.
            categories[cat if cat.isdigit() and len(cat)<=3 else "unknown"]+=1
            if not is_hospital(cat):
                for field in FIELDS:
                    if row[field].strip():other[field]+=1
                continue
            hosp+=1
            for field in FIELDS:
                state,code=classify(row[field])
                states[(field,state,code)]+=1
                batch.append(("qies",n,field,state,code))
                if len(batch)>=5000:
                    db.executemany("INSERT INTO qies_hospital_service_observations VALUES(?,?,?,?,?)",batch);batch.clear()
        if batch:db.executemany("INSERT INTO qies_hospital_service_observations VALUES(?,?,?,?,?)",batch)
        require(n==item["input_rows"] and hosp>0,"QIES input/scope mismatch")
        actual=db.execute("SELECT count(*) FROM qies_hospital_service_observations").fetchone()[0]
        require(actual==hosp*len(FIELDS)==sum(states.values()),"service observation count mismatch")
        for field,count in db.execute("SELECT field,count(*) FROM qies_hospital_service_observations GROUP BY field"):
            require(field in FIELDS and count==hosp,"field count mismatch")
        check_integrity(db)
    verify_raw(source,item)
    return {"source_records_verified":n,"hospital_category_rows":hosp,"service_observations":actual,
            "category_code_counts":dict(categories),"fields":{
            f:{"label":label,"value_distribution":{("code_"+c if c is not None else s):k for (field,s,c),k in states.items() if field==f}}
            for f,label in FIELDS.items()},"nonhospital_nonblank_values_not_interpreted":dict(other),
            "reference_domain":REFERENCE,"semantic_status":"catalog_linked_2023_layout_provisional_for_2026",
            "limitations":["Code distributions are from the actual Q3 2026 source; labels derive from the publisher-linked April 2023 layout, not a separately confirmed current dictionary.","Only hospital category 01 interpreted against historical reference; no nonhospital value interpretation.","No inference of ownership, installed machines, current operation, contractor, or procurement intent.","Aggregate audit only; local source-scoped database, not national integration or production."]}

def build(output,raw_dir,base_db,allow_download):
    item=next(s for s in load_lock(LOCK)["sources"] if s["family"]=="registry" and s["key"]=="qies")
    output=output.resolve();require(not output.exists(),"new output required");output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".qies-hospital-service-",dir=output.parent) as tmp:
        stage=Path(tmp);raw=stage/"raw";raw.mkdir();ready=stage/"ready";ready.mkdir()
        path=materialize(item,raw_dir,raw,allow_download)
        require(allow_download,"explicit dictionary download required")
        layout=dictionary_evidence(raw/"layout.pdf")
        dbpath=ready/"facilitysignal.sqlite3"
        before=sha(base_db) if base_db else None
        if base_db:
            with closing(readonly(base_db)) as src,closing(sqlite3.connect(dbpath)) as dst:
                check_integrity(src);src.backup(dst)
        else:
            fs.init(dbpath);registry.import_registry(dbpath,item["metadata"],path,item["sha256"],item["input_rows"])
        with closing(sqlite3.connect(dbpath)) as db:
            db.execute("PRAGMA foreign_keys=ON");audit=project(db,path,item,layout)
        if base_db:require(sha(base_db)==before,"baseline mutated")
        audit.update({"layout":layout,"source_sha256":item["sha256"],"source_period":item["release"],"database_sha256":sha(dbpath),"database_bytes":dbpath.stat().st_size,"base_database_sha256":before})
        (ready/"qies-hospital-services-audit.json").write_text(json.dumps(audit,indent=2)+"\n")
        os.rename(ready,output)
        print("QIES_HOSPITAL_SERVICE_VERIFIED",json.dumps(audit),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);p.add_argument("--raw-dir",type=Path);p.add_argument("--base-db",type=Path);p.add_argument("--download",action="store_true")
    a=p.parse_args();build(a.output,a.raw_dir,a.base_db,a.download)
