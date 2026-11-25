"""Qualify the public CMS QCOR hospital XLSX export; retain aggregate metadata only."""
import argparse
import hashlib
import json
import re
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import openpyxl

URL="https://qcor.cms.gov/downloadHospital2567"
REPORT="https://qcor.cms.gov/Hospital_2567_Reports"
MAX_BYTES=350_000_000
MAX_EXPANDED=2_000_000_000

def allowed(url):
    p=urlsplit(url)
    if p.scheme!="https" or p.hostname!="qcor.cms.gov" or p.port not in (None,443) or p.username or p.password:
        raise ValueError("unexpected QCOR URL")
    return url

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        allowed(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def request(url,accept):
    return urllib.request.build_opener(Redirect()).open(urllib.request.Request(allowed(url),
        headers={"User-Agent":"FacilitySignal-development/0.1","Accept":accept}),timeout=180)

def download(path):
    h=hashlib.sha256();n=0
    with request(URL,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") as r,path.open("wb") as f:
        mime=r.headers.get_content_type()
        final=allowed(r.geturl())
        for chunk in iter(lambda:r.read(1024*1024),b""):
            n+=len(chunk)
            if n>MAX_BYTES: raise ValueError("download limit")
            h.update(chunk);f.write(chunk)
        metadata={"content_type":mime,"last_modified":r.headers.get("Last-Modified"),"etag":r.headers.get("ETag"),"url":final}
    if not zipfile.is_zipfile(path): raise ValueError("response is not an XLSX ZIP")
    with zipfile.ZipFile(path) as z:
        if sum(x.file_size for x in z.infolist())>MAX_EXPANDED: raise ValueError("XLSX expanded size limit")
        if "xl/workbook.xml" not in z.namelist(): raise ValueError("not an XLSX workbook")
    return {"bytes":n,"sha256":h.hexdigest(),**metadata}

def normalized(value):
    return re.sub(r"[^a-z0-9]","",str(value).lower()) if value is not None else ""

def header_candidate(values):
    keys={normalized(x) for x in values if x is not None}
    id_cols={"cmscertificationnumber","ccn","providernumber","providerno","prvdrnum","cmsnumber","cmscertificationnumberccn"}
    event_cols={"surveyeventid","surveyeventidentifier","eventid","surveydat e".replace(" ",""),"dateofcmssurvey","dateofsurvey"}
    tag_cols={"deficiencytag","tag","tagcode","deficiencytags","tagdescription","deficiencydescription"}
    return bool(keys&id_cols and keys&(event_cols|tag_cols)) or bool(keys&event_cols and keys&tag_cols)

def inspect(path):
    results=[]
    book=openpyxl.load_workbook(path,read_only=True,data_only=True,keep_links=False)
    try:
        for sheet in book.worksheets:
            n=0;header=None;header_row=None;before=0;after=0
            # Read actual cells, not just the declared worksheet dimension.
            sheet.reset_dimensions()
            for ordinal,values in enumerate(sheet.iter_rows(values_only=True),1):
                if ordinal>2_000_000: raise ValueError("row limit")
                if not any(x is not None and x!="" for x in values): continue
                n+=1
                if header is None and ordinal<=10 and header_candidate(values):
                    # Only recognized header rows; no raw survey narratives, names or values in audit.
                    header=[str(x) if x is not None else "" for x in values]
                    if any(len(x)>150 or "\n" in x for x in header): raise ValueError("ambiguous header")
                    header_row=ordinal
                elif header is None: before+=1
                else: after+=1
            results.append({"sheet":sheet.title,"nonblank_rows":n,"recognized_header_row":header_row,
                            "header":header,"rows_before_header":before,"data_rows_after_header":after if header else None})
    finally:
        book.close()
    return results

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit",type=Path,required=True)
    args=p.parse_args()
    if args.audit.exists(): raise ValueError("audit output already exists")
    with tempfile.TemporaryDirectory(prefix="qcor-hospital-") as temp:
        path=Path(temp)/"hospital.xlsx"
        meta=download(path)
        sheets=inspect(path)
        audit={"source_id":"FS-020","publisher":"CMS QCOR","report_url":REPORT,
               "retrieved_at":datetime.now(timezone.utc).isoformat(),"download":meta,"sheets":sheets,
               "status":"downloaded_schema_probe","limitations":["Sheet data row counts are not unique survey or deficiency counts.",
                    "No independent source reconciliation, import, facility matching, reuse or privacy clearance yet.",
                    "Do not publish full workbook or survey narrative; official redaction still requires review."]}
        args.audit.parent.mkdir(parents=True,exist_ok=True)
        args.audit.write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        print("QCOR_PROBE",json.dumps(audit),flush=True)
        if not any(s["recognized_header_row"] for s in sheets):
            raise ValueError("no recognized survey/deficiency header; manual schema review required")

if __name__=="__main__":
    main()
