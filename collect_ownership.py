"""Qualified hospital/SNF PECOS enrollment, organization roles and CHOW projection."""
import argparse
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
from collect_registry import CATALOG,get_json,expected_rows,download,source_encoding,open_csv
from probe_ownership import TARGETS,select
from build_combined import sha,check_integrity,require
import csv

PINS={
"hospital-enrollment":("a13f9528-2640-4f67-b716-884abdbe822c",9120),
"hospital-owner":("5c50f5b1-90c7-43df-9d5e-8cc22a11a2d0",147029),
"hospital-chow":("a78e5b6a-d1ee-4078-98d1-1415c704a028",779),
"snf-enrollment":("92a8ea7b-7007-451a-90a3-7215c49345e0",14401),
"snf-owner":("e910a8eb-3e63-49a3-9586-2c82ee51a2ab",302718),
"snf-chow":("e3143536-7a28-41b3-8e29-f3b56047e3cd",5340)}
ENROLL=("ENROLLMENT ID","ASSOCIATE ID","CCN","NPI","ORGANIZATION NAME","DOING BUSINESS AS NAME","PROVIDER TYPE CODE","PROVIDER TYPE TEXT","ADDRESS LINE 1","ADDRESS LINE 2","CITY","STATE","ZIP CODE","MULTIPLE NPI FLAG","ORGANIZATION TYPE STRUCTURE","PROPRIETARY NONPROFIT")
ORG=("ENROLLMENT ID","ASSOCIATE ID","ORGANIZATION NAME","ASSOCIATE ID - OWNER","ORGANIZATION NAME - OWNER","DOING BUSINESS AS NAME - OWNER","ROLE CODE - OWNER","ROLE TEXT - OWNER","ASSOCIATION DATE - OWNER","PERCENTAGE OWNERSHIP","PRIVATE EQUITY COMPANY - OWNER","REIT - OWNER","MANAGEMENT SERVICES COMPANY - OWNER","CHAIN HOME OFFICE - OWNER")
CHOW=tuple(x+" - "+side for side in ("BUYER","SELLER") for x in ("ENROLLMENT ID","ASSOCIATE ID","CCN","NPI","ORGANIZATION NAME","DOING BUSINESS AS NAME"))+("CHOW TYPE CODE","CHOW TYPE TEXT","EFFECTIVE DATE")
TABLES={"enrollment":"pecos_enrollment_rows","owner":"pecos_org_role_rows","chow":"pecos_chow_rows"}

def init(db):
    db.executescript("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS pecos_releases(source TEXT PRIMARY KEY, period TEXT NOT NULL, modified TEXT NOT NULL, api TEXT NOT NULL, url TEXT NOT NULL, sha256 TEXT NOT NULL, expected_rows INTEGER NOT NULL, stored_rows INTEGER NOT NULL, excluded_individual_rows INTEGER NOT NULL, encoding TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS pecos_enrollment_rows(source TEXT NOT NULL REFERENCES pecos_releases(source), ordinal INTEGER NOT NULL, enrollment_id TEXT NOT NULL, pac_id TEXT NOT NULL, ccn TEXT NOT NULL, npi TEXT NOT NULL, organization_name TEXT NOT NULL, projection TEXT NOT NULL, PRIMARY KEY(source,ordinal));
    CREATE INDEX IF NOT EXISTS pecos_enrollment_id ON pecos_enrollment_rows(source,enrollment_id);
    CREATE INDEX IF NOT EXISTS pecos_enrollment_ccn ON pecos_enrollment_rows(source,ccn);
    CREATE TABLE IF NOT EXISTS pecos_org_role_rows(source TEXT NOT NULL REFERENCES pecos_releases(source), ordinal INTEGER NOT NULL, enrollment_id TEXT NOT NULL, pac_id TEXT NOT NULL, owner_pac_id TEXT NOT NULL, owner_name TEXT NOT NULL, role_code TEXT NOT NULL, role_text TEXT NOT NULL, projection TEXT NOT NULL, PRIMARY KEY(source,ordinal));
    CREATE INDEX IF NOT EXISTS pecos_role_enrollment ON pecos_org_role_rows(source,enrollment_id);
    CREATE INDEX IF NOT EXISTS pecos_role_owner ON pecos_org_role_rows(source,owner_pac_id);
    CREATE TABLE IF NOT EXISTS pecos_chow_rows(source TEXT NOT NULL REFERENCES pecos_releases(source), ordinal INTEGER NOT NULL, buyer_enrollment_id TEXT NOT NULL, seller_enrollment_id TEXT NOT NULL, buyer_ccn TEXT NOT NULL,seller_ccn TEXT NOT NULL, effective_date TEXT NOT NULL, projection TEXT NOT NULL, PRIMARY KEY(source,ordinal));
    """)

def fields(row, keys):
    result={}
    for k in keys:
        v=row[k].strip()
        if len(v)>1000 or "\x00" in v: raise ValueError("invalid projected field")
        result[k]=v
    return result

def project(kind,row):
    if kind=="owner":
        typ=row["TYPE - OWNER"].strip()
        if typ=="I": return None
        if typ!="O": raise ValueError("unknown owner type")
        p=fields(row,ORG)
        return (p["ENROLLMENT ID"],p["ASSOCIATE ID"],p["ASSOCIATE ID - OWNER"],p["ORGANIZATION NAME - OWNER"],p["ROLE CODE - OWNER"],p["ROLE TEXT - OWNER"],json.dumps(p,ensure_ascii=False,sort_keys=True))
    if kind=="enrollment":
        p=fields(row,ENROLL)
        return (p["ENROLLMENT ID"],p["ASSOCIATE ID"],p["CCN"],p["NPI"],p["ORGANIZATION NAME"],json.dumps(p,ensure_ascii=False,sort_keys=True))
    p=fields(row,CHOW)
    return (p["ENROLLMENT ID - BUYER"],p["ENROLLMENT ID - SELLER"],p["CCN - BUYER"],p["CCN - SELLER"],p["EFFECTIVE DATE"],json.dumps(p,ensure_ascii=False,sort_keys=True))

def ingest(db,key,meta,path,digest,expected):
    kind=key.split("-")[-1];table=TABLES[kind]
    required=set({"enrollment":ENROLL,"owner":ORG+("TYPE - OWNER",),"chow":CHOW}[kind])
    enc=source_encoding(path,meta["zipped"]);n=stored=excluded=0;invalid=Counter()
    with db:
        db.execute("INSERT INTO pecos_releases VALUES(?,?,?,?,?,?,?,?,?,?)",(key,meta["period"],meta["modified"],meta["api"],meta["url"],digest,expected,0,0,enc))
        with open_csv(path,meta["zipped"],enc) as f:
            reader=csv.DictReader(f)
            header=reader.fieldnames or []
            if len(header)!=len(set(header)) or not required.issubset(header): raise ValueError("CSV header mismatch")
            batch=[]
            for ordinal,row in enumerate(reader,2):
                n+=1
                if None in row or any(v is None for v in row.values()): raise ValueError("malformed CSV row")
                p=project(kind,row)
                if p is None:
                    excluded+=1;continue
                if kind in ("owner","enrollment"):
                    if not re.fullmatch(r"[A-Za-z0-9]{15}",p[0]): invalid["enrollment_id"]+=1
                    if not re.fullmatch(r"[0-9]{1,10}",p[1]): invalid["provider_pac_id"]+=1
                    if kind=="owner" and not re.fullmatch(r"[0-9]{1,10}",p[2]): invalid["owner_pac_id"]+=1
                    if kind=="enrollment" and not re.fullmatch(r"[A-Za-z0-9]{6}",p[2]): invalid["ccn_blank_or_nonstandard"]+=1
                batch.append((key,ordinal,*p));stored+=1
                if len(batch)>=5000:
                    db.executemany("INSERT INTO "+table+" VALUES("+",".join("?" for _ in batch[0])+")",batch);batch.clear()
            if batch: db.executemany("INSERT INTO "+table+" VALUES("+",".join("?" for _ in batch[0])+")",batch)
        require(n==expected and n==stored+excluded,"source count reconciliation failed")
        require(db.execute("SELECT count(*) FROM "+table+" WHERE source=?",(key,)).fetchone()[0]==stored,"stored count mismatch")
        db.execute("UPDATE pecos_releases SET stored_rows=?,excluded_individual_rows=? WHERE source=?",(stored,excluded,key))
    return {"input_rows":n,"stored_rows":stored,"excluded_individual_rows":excluded,"rejected_rows":0,"identifier_quality_flags":dict(invalid),"encoding":enc,"columns":header}

def audit_linkage(db):
    out={}
    for family in ("hospital","snf"):
        e=family+"-enrollment";o=family+"-owner"
        matched=db.execute("""SELECT count(*) FROM pecos_org_role_rows r WHERE source=? AND enrollment_id<>'' AND EXISTS (SELECT 1 FROM pecos_enrollment_rows e WHERE e.source=? AND e.enrollment_id=r.enrollment_id AND e.pac_id=r.pac_id AND e.pac_id<>'')""",(o,e)).fetchone()[0]
        total=db.execute("SELECT count(*) FROM pecos_org_role_rows WHERE source=?",(o,)).fetchone()[0]
        out[family]={"org_role_rows_exact_enrollment_and_pac":matched,"unmatched_org_role_rows":total-matched,"distinct_nonblank_enrollment_ids":db.execute("SELECT count(DISTINCT enrollment_id) FROM pecos_enrollment_rows WHERE source=? AND enrollment_id<>''",(e,)).fetchone()[0],"distinct_nonblank_ccns":db.execute("SELECT count(DISTINCT ccn) FROM pecos_enrollment_rows WHERE source=? AND ccn<>''",(e,)).fetchone()[0]}
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();require(not out.exists(),"new output required");out.parent.mkdir(parents=True,exist_ok=True)
    catalog=get_json(CATALOG);sources=[]
    with tempfile.TemporaryDirectory(prefix=".pecos-stage-",dir=out.parent) as tmp:
        stage=Path(tmp)/"ready";stage.mkdir();raw=Path(tmp)/"raw";raw.mkdir();dbpath=stage/"ownership.sqlite3"
        with closing(sqlite3.connect(dbpath)) as db:
            init(db)
            for key,(pin,n) in PINS.items():
                meta=select(catalog,TARGETS[key]);require(pin in meta["api"],"publisher release changed; review required")
                require(len(meta["distributions"])==1 and meta["distributions"][0]["format"]=="CSV","unexpected distribution")
                meta["url"]=meta["distributions"][0]["url"];meta["zipped"]=False
                require(expected_rows(meta)==n,"version count changed")
                path=raw/(key+".csv");digest,size=download(meta,path)
                result=ingest(db,key,meta,path,digest,n)
                require(expected_rows(meta)==n and sha(path)==digest,"post-import source drift")
                sources.append({"source":key,"metadata":meta,"sha256":digest,"bytes":size,**result})
                print("PECOS_IMPORTED",key,json.dumps({k:v for k,v in sources[-1].items() if k!="columns"}),flush=True)
            check_integrity(db)
            links=audit_linkage(db)
        audit={"retrieved_at":datetime.now(timezone.utc).isoformat(),"sources":sources,"linkage_candidates":links,"database_sha256":sha(dbpath),"database_bytes":dbpath.stat().st_size,"input_rows":sum(s["input_rows"] for s in sources),"stored_rows":sum(s["stored_rows"] for s in sources),"excluded_individual_rows":sum(s["excluded_individual_rows"] for s in sources),"note":"Organizational projection only; raw and individual records not retained; enrollment links are evidence candidates, not physical property ownership."}
        (stage/"ownership-manifest.json").write_text(json.dumps(audit,indent=2)+"\n")
        os.rename(stage,out)
        print("PECOS_VERIFIED",json.dumps({k:v for k,v in audit.items() if k!="sources"}),flush=True)

if __name__=="__main__":main()
