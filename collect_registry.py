"""Stage full CMS QIES/iQIES/CLIA public registry snapshots. Keep originals local; publish only audit aggregates."""
import argparse
import csv
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import urllib.request
import zipfile
from collections import Counter
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import facilitysignal as fs

ROOT="https://data.cms.gov"
CATALOG=ROOT+"/v1-1-data.json"
TITLES={"qies":"Provider of Services File - Quality Improvement and Evaluation System","iqies":"Provider of Services File - Internet Quality Improvement and Evaluation System","clia":"Provider of Services File - Clinical Laboratories"}
PINNED={"qies":"b1e5b072-5e82-4e37-9bd6-de8708679935","iqies":"8b2c0a70-7e47-4b0f-a592-e51eb315cead"}
MAX_DOWNLOAD=1_500_000_000
MAX_UNCOMPRESSED=3_000_000_000
ALIASES={
    "provider_id":["PRVDR_NUM","CLIA_LAB_NUM","CLIA_NUM","CLIA_ID","CLIA_NUMBER","CMS_CERTIFICATION_NUMBER"],
    "name":["FAC_NAME","LAB_NAME","LABORATORY_NAME","PROVIDER_NAME"],
    "address":["ST_ADR","ADDRESS","STREET_ADDRESS","LAB_ADR","LAB_ADDRESS"],
    "city":["CITY_NAME","CITY","LAB_CITY"],
    "state":["STATE_CD","STATE","LAB_STATE"],
    "zip":["ZIP_CD","ZIP_CODE","ZIP","LAB_ZIP"],
    "provider_type":["PRVDR_TYPE_ID","PRVDR_CTGRY_CD","LAB_TYPE_CD","LAB_TYPE"],
    "subtype":["PRVDR_SBTYP_ID","PRVDR_CTGRY_SBTYP_CD","LAB_SBTYP_CD"],
    "certification_date":["CRTFCTN_DT","CERTIFICATION_DATE","CERT_EFCTV_DT"],
    "termination_date":["TRMNTN_EXPRTN_DT","TERMINATION_DATE","CERT_EXPRTN_DT"],
    "status":["FED_CRTFCTN_STUS_NAME","FED_CRTFCTN_STUS_ID","CMPLNC_STUS_CD","PGM_TRMNTN_CD","CERT_STATUS"],
}
# An expiration date is not a termination date. Do not use CLIA certificate expiry as termination.
ALIASES["termination_date"].remove("CERT_EXPRTN_DT")
REQUIRED={"provider_id","name","address","city","state","zip"}

def allowed(url):
    p=urlsplit(url)
    if p.scheme!="https" or p.hostname!="data.cms.gov" or p.port not in (None,443) or p.username or p.password:
        raise ValueError("non-CMS URL")
    return url

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        allowed(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def response(url,accept):
    req=urllib.request.Request(allowed(url),headers={"User-Agent":"FacilitySignal-development/0.1","Accept":accept})
    return urllib.request.build_opener(Redirect()).open(req,timeout=90)

def get_json(url):
    with response(url,"application/json") as r:
        b=r.read(60_000_001)
    if len(b)>60_000_000: raise ValueError("metadata limit")
    return json.loads(b)

def choose(catalog,key):
    matches=[d for d in catalog.get("dataset",[]) if d.get("title")==TITLES[key]]
    if len(matches)!=1: raise ValueError("missing/ambiguous catalog title")
    d=matches[0]
    if d.get("accessLevel")!="public": raise ValueError("nonpublic access")
    dist=d.get("distribution",[])
    latest=[x for x in dist if x.get("format")=="API" and x.get("description")=="latest"]
    if len(latest)!=1 or not latest[0].get("temporal"): raise ValueError("ambiguous latest release")
    period=latest[0]["temporal"]
    versions=[x["accessURL"] for x in dist if x.get("format")=="API" and x.get("description")!="latest" and x.get("temporal")==period and x.get("accessURL")]
    if len(versions)!=1: raise ValueError("missing/ambiguous version-specific API")
    if key in PINNED and PINNED[key] not in versions[0]:
        raise ValueError("new version requires review")
    files=[x for x in dist if x.get("temporal")==period and x.get("downloadURL") and (x.get("format","").upper() in ("CSV","ZIP") or x.get("mediaType") in ("text/csv","application/zip"))]
    if len(files)!=1: raise ValueError("missing/ambiguous release file")
    file=files[0]
    zipped=file.get("format","").upper()=="ZIP" or file.get("mediaType")=="application/zip" or file["downloadURL"].lower().endswith(".zip")
    return {"registry":key,"title":d["title"],"period":period,"modified":d.get("modified"),"license":d.get("license"),"api":allowed(versions[0]),"url":allowed(file["downloadURL"]),"zipped":zipped}

def expected_rows(meta):
    d=get_json(meta["api"]+"/stats")
    n=d.get("total_rows")
    if isinstance(n,str) and n.isdigit(): n=int(n)
    if type(n)!=int or n<=0: raise ValueError("invalid version API count")
    return n

def download(meta,dest):
    h=hashlib.sha256()
    size=0
    with response(meta["url"],"application/zip" if meta["zipped"] else "text/csv") as r,dest.open("wb") as f:
        while chunk:=r.read(1024*1024):
            size+=len(chunk)
            if size>MAX_DOWNLOAD: raise ValueError("download limit exceeded")
            h.update(chunk);f.write(chunk)
    return h.hexdigest(),size

@contextmanager
def open_csv(path,zipped):
    if zipped:
        with zipfile.ZipFile(path) as z:
            entries=[i for i in z.infolist() if not i.is_dir() and i.filename.lower().endswith(".csv")]
            if len(entries)!=1 or entries[0].file_size>MAX_UNCOMPRESSED:
                raise ValueError("unexpected ZIP CSV content")
            with z.open(entries[0]) as b,io.TextIOWrapper(b,encoding="utf-8-sig",newline="") as f:
                yield f
    else:
        with path.open(encoding="utf-8-sig",newline="") as f: yield f

def mapping(headers):
    if not headers: raise ValueError("no CSV header")
    normalized={h.strip().upper():h for h in headers}
    if len(normalized)!=len(headers): raise ValueError("duplicate normalized headers")
    result={key:next((normalized[h] for h in choices if h in normalized),None) for key,choices in ALIASES.items()}
    missing=sorted(k for k in REQUIRED if result[k] is None)
    if missing: raise ValueError("unmapped required columns: "+",".join(missing))
    return result

def import_registry(db_path,meta,path,digest,expected):
    key=meta["registry"]
    with open_csv(path,meta["zipped"]) as f:
        reader=csv.DictReader(f)
        print("REGISTRY_COLUMNS",key,json.dumps(reader.fieldnames),flush=True)
        cols=mapping(reader.fieldnames)
        with closing(fs.connect(db_path)) as db,db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM certification_releases WHERE registry=?",(key,)).fetchone():
                raise ValueError("registry already exists in output")
            db.execute("INSERT INTO certification_releases VALUES(?,?,?,?,?,?,?,?,?)",(key,meta["title"],meta["period"],meta["api"],meta["url"],digest,expected,datetime.now(timezone.utc).isoformat(),json.dumps(cols,sort_keys=True)))
            batch=[];n=0;missing_ids=0
            for row in reader:
                if None in row or any(v is None for v in row.values()): raise ValueError("malformed row "+str(n+1))
                n+=1
                h=hashlib.sha256(json.dumps(list(row.values()),ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
                vals=[row[cols[k]].strip() if cols[k] else "" for k in ALIASES]
                missing_ids+=not bool(vals[0])
                batch.append((key,n,h,*vals))
                if len(batch)>=5000:
                    db.executemany("INSERT INTO certification_records VALUES("+",".join("?" for _ in range(14))+")",batch);batch.clear()
            if batch: db.executemany("INSERT INTO certification_records VALUES("+",".join("?" for _ in range(14))+")",batch)
            if n!=expected: raise ValueError("row count mismatch expected=%d received=%d"%(expected,n))
            unique_ids=db.execute("SELECT count(DISTINCT provider_id) FROM certification_records WHERE registry=? AND provider_id<>''",(key,)).fetchone()[0]
            duplicate_rows=n-db.execute("SELECT count(DISTINCT row_sha256) FROM certification_records WHERE registry=?",(key,)).fetchone()[0]
            states=fs.rows(db,"SELECT state,count(*) AS records FROM certification_records WHERE registry=? GROUP BY state ORDER BY state",(key,))
    return {"registry":key,"rows":n,"unique_nonblank_ids":unique_ids,"missing_ids":missing_ids,"repeated_id_rows":n-missing_ids-unique_ids,"exact_duplicate_rows":duplicate_rows,"states":states,"mapping":cols}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--base-db",type=Path)
    p.add_argument("--datasets",nargs="+",choices=TITLES,default=list(TITLES))
    args=p.parse_args()
    out=args.output.resolve()
    if out.exists() or len(set(args.datasets))!=len(args.datasets):
        p.error("output must be new and source list unique")
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".registry-stage-",dir=out.parent) as tmp:
        ready=Path(tmp)/"ready";ready.mkdir()
        raw=ready/"raw";raw.mkdir()
        db_path=ready/"facilitysignal.sqlite3"
        if args.base_db:
            if not args.base_db.is_file(): raise ValueError("base database missing")
            with closing(sqlite3.connect(args.base_db.resolve().as_uri()+"?mode=ro",uri=True)) as src,closing(sqlite3.connect(db_path)) as dst:
                if src.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise ValueError("base DB integrity")
                src.backup(dst)
        fs.init(db_path)
        catalog=get_json(CATALOG)
        manifest=[]
        for key in args.datasets:
            meta=choose(catalog,key)
            print("REGISTRY_RELEASE",key,json.dumps(meta),flush=True)
            n=expected_rows(meta)
            path=raw/(key+(".zip" if meta["zipped"] else ".csv"))
            digest,size=download(meta,path)
            if expected_rows(meta)!=n: raise ValueError("version API count changed")
            print("REGISTRY_DOWNLOADED",key,n,size,digest,flush=True)
            result=import_registry(db_path,meta,path,digest,n)
            print("REGISTRY_IMPORTED",key,json.dumps({k:v for k,v in result.items() if k not in ("states","mapping")}),flush=True)
            manifest.append({"source":meta,"bytes":size,"sha256":digest,**result})
        # Confirm catalog still resolves the same release selections; fail closed on a mid-run refresh.
        fresh=get_json(CATALOG)
        for item in manifest:
            if choose(fresh,item["registry"])!=item["source"]: raise ValueError("catalog changed during run")
        with closing(fs.connect(db_path)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or db.execute("PRAGMA foreign_key_check").fetchone(): raise ValueError("integrity check failed")
            total=db.execute("SELECT count(*) FROM certification_records").fetchone()[0]
            if total!=sum(x["rows"] for x in manifest): raise ValueError("registry reconciliation failure")
        with db_path.open("rb") as f: db_hash=hashlib.file_digest(f,"sha256").hexdigest()
        audit={"sources":manifest,"certification_records":total,"db_sha256":db_hash,"note":"Registry source rows including historical/terminated; never add to active provider count."}
        (ready/"registry-manifest.json").write_text(json.dumps(audit,indent=2)+"\n")
        print("REGISTRY_VERIFIED",total,db_hash,flush=True)
        os.rename(ready,out)

if __name__=="__main__": main()
