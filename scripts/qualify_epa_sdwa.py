"""Qualify EPA's national SDWA search release, with aggregate-only retained evidence.
No water-system locations, names, contact information, internal assets, individual
violation details, healthcare linkage or public row-level publication.
"""
import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import tempfile
import urllib.request
import zipfile
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit

URL="https://echo.epa.gov/files/echodownloads/SDWA_system_search_download.zip"
DOC="https://echo.epa.gov/tools/data-downloads/sdwa-facility-search-download-summary"
MAX_DOWNLOAD=100*1024*1024
MAX_EXPANDED=750*1024*1024
REQUIRED={"PWSID","STATE_CODE","PWS_TYPE_CODE","PWS_ACTIVITY_CODE","SERVICE_AREA_TYPE_CODE"}
MEMBER="SDWA_SYSTEM_SEARCH.csv"

def require(ok,message):
    if not ok:raise ValueError(message)

def allowed(url):
    p=urlsplit(url)
    return p.scheme=="https" and p.netloc=="echo.epa.gov" and p.path==urlsplit(URL).path and not p.query and not p.fragment

class NoUnexpectedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        require(allowed(newurl),"unapproved redirect")
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def download(path):
    opener=urllib.request.build_opener(NoUnexpectedRedirect())
    req=urllib.request.Request(URL,headers={"User-Agent":"FacilitySignal source qualification (one national publisher download)","Accept":"application/zip,application/octet-stream"})
    h=hashlib.sha256();n=0
    with opener.open(req,timeout=90) as res,path.open("xb") as out:
        require(allowed(res.geturl()),"unapproved response URL")
        length=res.headers.get("Content-Length")
        if length:require(0<int(length)<=MAX_DOWNLOAD,"download exceeds budget")
        while chunk:=res.read(1024*1024):
            n+=len(chunk);require(n<=MAX_DOWNLOAD,"download exceeds budget")
            h.update(chunk);out.write(chunk)
        require(n>0 and (not length or n==int(length)),"incomplete download")
        return {"url":URL,"sha256":h.hexdigest(),"bytes":n,"retrieved_at":datetime.now(timezone.utc).isoformat(),
                "last_modified":res.headers.get("Last-Modified"),"etag":res.headers.get("ETag")}

def bounded_code(value,width=12):
    s=value.strip()
    if not s:return "(blank)"
    return s if re.fullmatch(r"[A-Z0-9_-]{1,"+str(width)+r"}",s) else "(unrecognized)"

def key_format(key):
    # EPA Federal Reporting Services dictionary explicitly documents UTAH + 5 digits.
    # EPA FRDS data entry instructions identify numeric region prefixes 01 through 10.
    # Do not infer a location, change identifiers, or accept other shapes.
    if re.fullmatch(r"[A-Z]{2}[0-9]{7}",key):return "standard"
    if re.fullmatch(r"UTAH[0-9]{5}",key):return "utah"
    if re.fullmatch(r"(?:0[1-9]|10)[0-9]{7}",key):return "epa_region"
    if not key:return "blank"
    if len(key)!=9:return "wrong_length"
    return "other_nine_character"

def ingest(db,path,encoding="utf-8-sig"):
    with zipfile.ZipFile(path) as z:
        members=z.infolist()
        require(len(members)==1 and members[0].filename==MEMBER,"unexpected archive membership")
        require(0<members[0].file_size<=MAX_EXPANDED,"expanded size exceeds budget")
        require(not members[0].flag_bits&1,"encrypted archive")
        db.execute("CREATE TABLE pws_key(pwsid TEXT PRIMARY KEY,state TEXT NOT NULL,kind TEXT NOT NULL,activity TEXT NOT NULL)")
        input_rows=0;invalid=0;duplicate=0;states=Counter();types=Counter();activity=Counter();blank_fields=Counter();formats=Counter();invalid_formats=Counter()
        with db,z.open(members[0]) as raw,io.TextIOWrapper(raw,encoding=encoding,newline="") as stream:
            reader=csv.DictReader(stream,strict=True)
            headers=reader.fieldnames or []
            require(len(headers)==len(set(headers)) and REQUIRED<=set(headers),"required source columns missing or duplicate")
            for row in reader:
                input_rows+=1
                require(None not in row and all(v is not None for v in row.values()),"malformed CSV row")
                for field in REQUIRED:
                    if not row[field].strip():blank_fields[field]+=1
                key=row["PWSID"].strip()
                fmt=key_format(key)
                if fmt not in {"standard","utah","epa_region"}:
                    invalid+=1;invalid_formats[fmt]+=1;continue
                formats[fmt]+=1
                state=bounded_code(row["STATE_CODE"],2);kind=bounded_code(row["PWS_TYPE_CODE"],6)
                act=bounded_code(row["PWS_ACTIVITY_CODE"],1)
                cursor=db.execute("INSERT OR IGNORE INTO pws_key VALUES(?,?,?,?)",(key,state,kind,act))
                if cursor.rowcount!=1:duplicate+=1;continue
                states[state]+=1;types[kind]+=1;activity[act]+=1
            stored=db.execute("SELECT count(*) FROM pws_key").fetchone()[0]
            require(input_rows==stored+duplicate+invalid and stored>0,"row reconciliation")
            require(sum(states.values())==sum(types.values())==sum(activity.values())==stored,"distribution reconciliation")
            require(sum(formats.values())==stored+duplicate and sum(invalid_formats.values())==invalid,"format reconciliation")
            require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite integrity failed")
        return {"header":headers,"columns":len(headers),"encoding":encoding,"expanded_bytes":members[0].file_size,
                "input_rows":input_rows,"stored_unique_pws_keys":stored,"duplicate_keys":duplicate,"invalid_keys":invalid,
                "state_code_count":len(states),"system_type_counts":dict(types),"activity_code_counts":dict(activity),
                "blank_required_fields":dict(blank_fields),"accepted_key_format_counts":dict(formats),"invalid_key_format_counts":dict(invalid_formats),
                "qualification":"clean_keys" if duplicate==invalid==0 else "key_anomalies_require_review",
                "limits":"Ephemeral key/type/status projection, no healthcare attribution or current facility operation inference. Source codes not reinterpreted. No row-level artifact."}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit already exists")
    with tempfile.TemporaryDirectory(prefix="epa-sdwa-") as tmp:
        path=Path(tmp)/"source.zip";meta=download(path)
        with closing(sqlite3.connect(":memory:")) as db:
            try:audit=ingest(db,path)
            except UnicodeDecodeError:
                # Retry only the local archive, not the network; record chosen encoding.
                db.rollback();db.execute("DROP TABLE IF EXISTS pws_key")
                audit=ingest(db,path,"cp1252")
        meta.update(audit)
        require(hashlib.file_digest(path.open("rb"),"sha256").hexdigest()==meta["sha256"],"source mutated")
    meta.update({"comparison_baseline_sha256":"cad153417ac7f22726bd4b5ebe1cb4aca6088b45910a0b343324fc82cf78ce21","same_bytes_as_failed_run":meta["sha256"]=="cad153417ac7f22726bd4b5ebe1cb4aca6088b45910a0b343324fc82cf78ce21","dictionary_url":DOC,"publication_date":None,"reuse_review":"pending","retention":"aggregate audit only"})
    a.audit.parent.mkdir(parents=True,exist_ok=True);a.audit.write_text(json.dumps(meta,indent=2)+"\n")
    print("EPA_SDWA_QUALIFICATION",json.dumps(meta),flush=True)
    require(meta["qualification"]=="clean_keys","key anomalies: inspect aggregate audit before correction")

if __name__=="__main__":main()
