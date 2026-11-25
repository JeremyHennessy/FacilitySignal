"""Download versioned CMS bulk data; compare independent API counts; build an isolated validated snapshot."""
import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import urllib.request
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
import facilitysignal as fs

BASE = "https://data.cms.gov/provider-data"
MAX_BYTES = 350_000_000
MAX_JSON = 8_000_000

def allowed(url):
    p = urlsplit(url)
    if p.scheme != "https" or p.hostname != "data.cms.gov" or p.port not in (None,443) or p.username or p.password or not p.path.startswith("/provider-data/"):
        raise ValueError("non-CMS URL")
    return url

class CMSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def response(url):
    req = urllib.request.Request(allowed(url),headers={"User-Agent":"FacilitySignal/0.2 public data ingestion"})
    return urllib.request.build_opener(CMSRedirect()).open(req,timeout=45)

def get_json(url):
    with response(url) as r:
        content=r.read(MAX_JSON+1)
        if len(content)>MAX_JSON:
            raise ValueError("JSON limit exceeded")
        return json.loads(content)

def metadata(ident):
    data=get_json(BASE+"/api/1/metastore/schemas/dataset/items/"+ident)
    if data.get("identifier")!=ident or data.get("accessLevel")!="public":
        raise ValueError("unexpected dataset identity/access")
    urls=[d["downloadURL"] for d in data.get("distribution",[]) if d.get("mediaType")=="text/csv" and d.get("downloadURL")]
    if len(urls)!=1 or not data.get("released"):
        raise ValueError("ambiguous CSV distribution or release missing")
    return {"id":ident,"released":data["released"],"modified":data.get("modified"),"url":allowed(urls[0])}

def count(ident):
    data=get_json(BASE+"/api/1/datastore/query/"+ident+"/0?limit=1&offset=0")
    n=data.get("count")
    if type(n)!=int or n<=0 or len(data.get("results",[]))!=1:
        raise ValueError("unexpected API count")
    return n

def download(key, folder):
    ident=fs.CATALOG[key][0]
    meta=metadata(ident)
    n=count(ident)
    dest=folder/(key+".csv")
    h=hashlib.sha256()
    size=0
    with response(meta["url"]) as r, dest.open("wb") as f:
        while chunk:=r.read(1024*1024):
            size+=len(chunk)
            if size>MAX_BYTES:
                raise ValueError("CSV limit exceeded")
            h.update(chunk)
            f.write(chunk)
    if metadata(ident)!=meta or count(ident)!=n:
        raise ValueError("CMS source changed during download")
    # No rows printed in public CI logs.
    with dest.open(encoding="utf-8-sig",newline="") as f:
        header=next(csv.reader(f))
    return {"dataset":key,"metadata":meta,"expected_rows":n,"sha256":h.hexdigest(),"bytes":size,"columns":header,"path":dest}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True,help="New directory for snapshot and audit manifest")
    parser.add_argument("--datasets",nargs="+",choices=sorted(fs.CATALOG),default=sorted(fs.CATALOG))
    args=parser.parse_args()
    dest=args.output.resolve()
    if dest.exists():
        parser.error("output directory already exists; never overwrite an existing snapshot")
    if len(set(args.datasets))!=len(args.datasets):
        parser.error("duplicate dataset arguments")
    dest.parent.mkdir(parents=True,exist_ok=True)
    # Stage in sibling directory so publication is atomic on the same filesystem.
    with tempfile.TemporaryDirectory(prefix=".cms-stage-",dir=dest.parent) as tmp:
        temp=Path(tmp)
        raw=temp/"raw"
        raw.mkdir()
        ready=temp/"ready"
        ready.mkdir()
        manifest=[]
        failures=[]
        # Bounded concurrency; every dataset must be qualified before a snapshot is published.
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(download,k,raw):k for k in args.datasets}
            downloads={}
            for future in concurrent.futures.as_completed(futures):
                key=futures[future]
                try:
                    info=future.result()
                    downloads[key]=info
                    print("DOWNLOADED",key,info["expected_rows"],info["bytes"],"release",info["metadata"]["released"],flush=True)
                except Exception as e:
                    # Avoid printing potentially sensitive raw CSV values.
                    print("DOWNLOAD FAILED",key,type(e).__name__,str(e)[:250],flush=True)
                    failures.append(key)
        if failures:
            raise SystemExit("download failures: "+",".join(sorted(failures)))
        db=ready/"facilitysignal.sqlite3"
        for key in args.datasets:
            item=downloads[key]
            try:
                result=fs.import_csv(db,key,item["path"],item["metadata"]["released"],item["expected_rows"])
                if result.get("sha256")!=item["sha256"] or result["input_rows"]!=item["expected_rows"]:
                    raise ValueError("import and download manifest mismatch")
                print("IMPORTED",key,json.dumps(result),flush=True)
                manifest.append({k:v for k,v in item.items() if k!="path"}|{"import":result})
            except Exception as e:
                print("IMPORT FAILED",key,type(e).__name__,str(e)[:220],"COLUMNS",item["columns"][:25],flush=True)
                failures.append(key)
        if failures:
            raise SystemExit("import failures: "+",".join(sorted(failures)))
        with closing(fs.connect(db)) as conn:
            if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise RuntimeError("database integrity failure")
            if conn.execute("PRAGMA foreign_key_check").fetchone():
                raise RuntimeError("database foreign key failure")
            overview=fs.overview(conn)
            facility_by_source=fs.rows(conn,"SELECT dataset, count(*) AS records,count(DISTINCT state) AS jurisdictions FROM facilities GROUP BY dataset ORDER BY dataset")
            findings_by_source=fs.rows(conn,"SELECT dataset,count(*) AS records,count(DISTINCT ccn) AS providers FROM findings GROUP BY dataset ORDER BY dataset")
            unmatched=fs.rows(conn,"SELECT d.dataset,count(*) AS records FROM findings d WHERE NOT EXISTS (SELECT 1 FROM facilities f WHERE f.dataset='nursing' AND f.ccn=d.ccn) GROUP BY d.dataset")
        summary={"facility_records":overview["facility_records"],"finding_records":overview["finding_records"],"by_state":overview["by_state"],"facility_by_source":facility_by_source,"findings_by_source":findings_by_source,"unmatched_nursing_citations":unmatched,"sources":manifest,"db_sha256":hashlib.file_digest(db.open("rb"),"sha256").hexdigest()}
        (ready/"manifest.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
        print("VERIFIED SUMMARY",json.dumps({k:v for k,v in summary.items() if k not in ("sources","by_state")}),flush=True)
        print("REPRESENTED JURISDICTIONS",",".join(sorted(x["state"] for x in overview["by_state"])),flush=True)
        os.rename(ready,dest)

if __name__=="__main__":
    main()
