"""AHRQ 2023 Compendium source qualification. Aggregate evidence only."""
import argparse
import csv
import hashlib
import json
import re
import tempfile
import urllib.request
import zipfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT="https://www.ahrq.gov/sites/default/files/wysiwyg/chsp/compendium/"
LANDING="https://www.ahrq.gov/chsp/data-resources/compendium-2023.html"
SOURCES={"system":"chsp-compendium-2023-rev.csv","hospital":"chsp-hospital-linkage-2023.csv","nursing":"chsp-nh-linkage-2023.csv","home-health":"chsp-hhco-linkage-2023.csv","outpatient":"chsp-os-linkage-2023.xlsx"}
MAX_BYTES=80_000_000
MAX_EXPANDED=700_000_000
MAX_ROWS=2_000_000

def require(ok,reason):
    if not ok: raise ValueError(reason)

def allowed(url):
    p=urlsplit(url)
    require(p.scheme=="https" and p.hostname=="www.ahrq.gov" and p.port in (None,443) and not p.username and not p.password and url in {ROOT+x for x in SOURCES.values()},"unexpected AHRQ URL")
    return url

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        allowed(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def download(key,path):
    url=allowed(ROOT+SOURCES[key]);h=hashlib.sha256();size=0
    req=urllib.request.Request(url,headers={"User-Agent":"FacilitySignal-development/0.1","Accept":"application/octet-stream,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})
    with urllib.request.build_opener(Redirect()).open(req,timeout=90) as resp,path.open("xb") as out:
        allowed(resp.geturl())
        for chunk in iter(lambda:resp.read(1024*1024),b""):
            size+=len(chunk);require(size<=MAX_BYTES,"download exceeds limit")
            h.update(chunk);out.write(chunk)
        meta={"url":url,"bytes":size,"sha256":h.hexdigest(),"mime":resp.headers.get_content_type(),"last_modified":resp.headers.get("Last-Modified"),"etag":resp.headers.get("ETag")}
    require(size>0,"empty source")
    return meta

def headers(values):
    cols=[str(x).strip() if x is not None else "" for x in values]
    require(bool(cols) and all(re.fullmatch(r"[A-Za-z0-9_ .()/&-]{1,120}",x) for x in cols),"invalid source header")
    require(len({x.casefold() for x in cols})==len(cols),"duplicate header")
    return cols

def csv_probe(path,kind,system_ids=None):
    from collections import Counter
    with path.open("r",encoding="utf-8-sig",errors="strict",newline="") as f:
        reader=csv.DictReader(f);cols=headers(reader.fieldnames or [])
        require(reader.fieldnames==cols,"unexpected header whitespace")
        if kind in ("system","hospital"):require("health_sys_id" in cols,"documented system identifier absent")
        if kind=="hospital":require({"ccn","compendium_hospital_id"}.issubset(cols),"documented hospital identifier absent")
        n=linked=unknown=missing_ccn=nonstandard_ccn=0
        ids=set();id_duplicates=0;missing_id=0
        ccn_counts=Counter()
        id_field="health_sys_id" if kind=="system" else "compendium_hospital_id" if kind=="hospital" else None
        for row in reader:
            n+=1;require(n<=MAX_ROWS,"row limit")
            require(None not in row and all(v is not None for v in row.values()),"malformed CSV row")
            sysid=row.get("health_sys_id","").strip()
            if sysid and sysid.upper() not in ("NA","N/A",".","NULL"):
                linked+=1
                if system_ids is not None and sysid not in system_ids:unknown+=1
            if id_field:
                ident=row[id_field].strip()
                if not ident or ident.upper() in ("NA","N/A",".","NULL"): missing_id+=1
                elif ident in ids:id_duplicates+=1
                else:ids.add(ident)
            if kind=="hospital":
                ccn=row["ccn"].strip()
                if not ccn or ccn.upper() in ("NA","N/A",".","NULL"):missing_ccn+=1
                else:
                    ccn_counts[ccn]+=1
                    if not re.fullmatch("[A-Za-z0-9]{6}",ccn):nonstandard_ccn+=1
    require(n>0,"empty source table")
    result={"rows":n,"columns":cols,"nonmissing_system_id_rows":linked if "health_sys_id" in cols else None,"system_id_not_in_system_file":unknown if system_ids is not None and "health_sys_id" in cols else None}
    if id_field:result.update({"documented_id_field":id_field,"missing_ids":missing_id,"duplicate_id_rows":id_duplicates})
    if kind=="hospital":result.update({"missing_ccn":missing_ccn,"nonstandard_ccn":nonstandard_ccn,"repeated_ccn_rows":sum(v-1 for v in ccn_counts.values())})
    return result,ids

def xlsx_probe(path):
    import openpyxl
    require(zipfile.is_zipfile(path),"not an XLSX")
    with zipfile.ZipFile(path) as z:
        require(sum(x.file_size for x in z.infolist())<=MAX_EXPANDED,"expanded XLSX limit")
        require("xl/workbook.xml" in z.namelist(),"not an XLSX workbook")
    book=openpyxl.load_workbook(path,read_only=True,data_only=True,keep_links=False)
    result=[]
    try:
        for sheet in book.worksheets:
            sheet.reset_dimensions();cols=None;n=0
            for ordinal,row in enumerate(sheet.iter_rows(values_only=True),1):
                require(ordinal<=MAX_ROWS,"worksheet row limit")
                if not any(x is not None and x!="" for x in row):continue
                if cols is None:
                    cols=headers(row)
                else:n+=1
            require(cols is not None and n>0,"empty worksheet")
            result.append({"sheet":sheet.title,"rows_after_header":n,"columns":cols})
    finally:book.close()
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    result={"publisher":"AHRQ","landing":LANDING,"vintage":2023,"retrieved_at":datetime.now(timezone.utc).isoformat(),"sources":{},"limitations":["Not current affiliations or parcel ownership. Underlying AHA and IQVIA data require separate commercial-reuse review; no row-level output.","Counts from publisher documentation are checked for system/hospital files; other row counts are observed, not independently reconciled."]}
    with tempfile.TemporaryDirectory(prefix="ahrq-source-probe-") as tmp:
        system_ids=None
        for kind,name in SOURCES.items():
            path=Path(tmp)/name;meta=download(kind,path)
            if kind=="outpatient":stats={"sheets":xlsx_probe(path)}
            else:
                stats,ids=csv_probe(path,kind,system_ids)
                if kind=="system":system_ids=ids
            result["sources"][kind]={"download":meta,"audit":stats}
            print("AHRQ_SOURCE",kind,json.dumps(result["sources"][kind]),flush=True)
            path.unlink()
    s=result["sources"]["system"]["audit"];h=result["sources"]["hospital"]["audit"]
    require(s["rows"]==639 and s["missing_ids"]==0 and s["duplicate_id_rows"]==0,"system documented count/key mismatch")
    require(h["rows"]==6800 and h["nonmissing_system_id_rows"]==4193 and h["system_id_not_in_system_file"]==0 and h["missing_ids"]==0 and h["duplicate_id_rows"]==0,"hospital documented count/key/link mismatch")
    a.audit.parent.mkdir(parents=True,exist_ok=True);a.audit.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print("AHRQ_PROBE_VERIFIED",len(result["sources"]),flush=True)
if __name__=="__main__":main()
