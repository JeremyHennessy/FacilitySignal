"""Bounded public QCOR ASC and X-ray workbook qualification, aggregate evidence only."""
import argparse, hashlib, json, re, sqlite3, tempfile, zipfile
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import openpyxl
from scripts.probe_qcor_hospital import request, normalized, header_candidate
from collect_qcor_hospital import survey_date
from build_combined import require

SOURCES={
 "asc":("FS-025","https://qcor.cms.gov/ASC_2567_Reports","https://qcor.cms.gov/downloadASC2567","C"),
 "xray":("FS-028","https://qcor.cms.gov/X-Ray_Supplier_2567_Reports","https://qcor.cms.gov/downloadXRAY2567","X"),
}
MAX_BYTES=150_000_000
MAX_EXPANDED=1_000_000_000
ALIASES={
 "ccn":{"ccn","cmscertificationnumber","cmscertificationnumberccn","providernumber"},
 "event":{"surveyeventid","surveyeventidentifier","eventid"},
 "date":{"surveydate","dateofcmssurvey","dateofsurvey"},
 "tag":{"deficiencytag","tag","tagcode"},
 "kind":{"deficiencytagtype","tagtype"},
}

def download(key,path):
    _,_,url,_=SOURCES[key];h=hashlib.sha256();size=0
    with request(url,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") as res,path.open("xb") as f:
        require(res.geturl()==url,"unexpected final download URL")
        while chunk:=res.read(1024*1024):
            size+=len(chunk);require(size<=MAX_BYTES,"download limit")
            h.update(chunk);f.write(chunk)
        meta={"url":url,"bytes":size,"sha256":h.hexdigest(),"last_modified":res.headers.get("Last-Modified"),
              "etag":res.headers.get("ETag"),"retrieved_at":datetime.now(timezone.utc).isoformat()}
    require(zipfile.is_zipfile(path),"not XLSX")
    with zipfile.ZipFile(path) as z:
        require(len(z.infolist())<=2000 and sum(x.file_size for x in z.infolist())<=MAX_EXPANDED,"archive limit")
        require("xl/workbook.xml" in z.namelist(),"not workbook")
    return meta

def map_header(header):
    keys=[normalized(x) for x in header]
    require(0<len(keys)<=80 and all(keys) and len(set(keys))==len(keys),"ambiguous header")
    result={}
    for k,aliases in ALIASES.items():
        hits=[i for i,n in enumerate(keys) if n in aliases]
        if len(hits)==1:result[k]=hits[0]
    return result

def classify(values,m,key):
    def get(k):
        i=m[k];return "" if i>=len(values) or values[i] is None else str(values[i]).strip()
    ccn=get("ccn").upper()
    require(re.fullmatch(r"[0-9]{2}"+SOURCES[key][3]+r"[0-9]{7}",ccn) is not None,"provider_key_shape")
    event=get("event").upper()
    require(len(event)<=32 and re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*",event) is not None,"event_key_shape")
    try: day=survey_date(values[m["date"]] if m["date"]<len(values) else None)
    except ValueError:raise ValueError("survey_date_shape") from None
    tag=get("tag").upper();kind=get("kind").casefold()
    require(not tag or re.fullmatch(r"[A-Z][0-9]{4}",tag) is not None,"tag_key_shape")
    require(bool(tag) or not kind,"missing_tag_with_type")
    state="memo" if kind=="memo" or re.fullmatch(r"[A-Z]0000",tag) else "nonmemo_tag" if tag else "no_tag_reported"
    return ccn,event,day,state

def inspect(path,key):
    book=openpyxl.load_workbook(path,read_only=True,data_only=True,keep_links=False)
    try:
        require(len(book.worksheets)==1,"unexpected sheet count")
        sheet=book.worksheets[0];sheet.reset_dimensions()
        rows=iter(sheet.iter_rows(values_only=True))
        first=tuple(next(rows,()))
        require(header_candidate(first),"unrecognized header; no source values emitted")
        require(all(isinstance(x,str) and 0<len(x)<=150 and "\n" not in x and "\r" not in x for x in first),"header shape")
        m=map_header(first);ready=set(m)==set(ALIASES)
        kinds=Counter();reject=Counter();total=0;blank=0;events=set();ccns=set();event_nonmemo=set()
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE TABLE survey(ordinal INTEGER PRIMARY KEY,ccn TEXT NOT NULL,event TEXT NOT NULL,day TEXT NOT NULL,kind TEXT NOT NULL)")
            for ordinal,values in enumerate(rows,2):
                require(ordinal<=500001,"row limit")
                if not any(v is not None and v!="" for v in values):blank+=1;continue
                total+=1
                if not ready:continue
                if len(values)>len(first):reject["extra_columns"]+=1;continue
                try:c,e,d,k=classify(values,m,key)
                except ValueError as exc:reject[str(exc)]+=1;continue
                db.execute("INSERT INTO survey VALUES(?,?,?,?,?)",(ordinal,c,e,d,k))
                kinds[k]+=1;ccns.add(c);events.add((c,e,d))
                if k=="nonmemo_tag":event_nonmemo.add((c,e,d))
            db.commit()
            stored=db.execute("SELECT COUNT(*) FROM survey").fetchone()[0]
            require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite integrity")
            if ready:
                require(total==stored+sum(reject.values()) and stored==sum(kinds.values()),"row reconciliation")
                require(db.execute("SELECT COUNT(*) FROM (SELECT DISTINCT ccn,event,day FROM survey)").fetchone()[0]==len(events),"event reconciliation")
            return {"source_id":SOURCES[key][0],"report_url":SOURCES[key][1],"sheet_count":1,
                    "header":list(first),"columns":len(first),"field_mapping":{k:first[i] for k,i in m.items()},
                    "mapping_complete":ready,"input_rows":total,"blank_rows":blank,"stored_rows":stored,
                    "rejected_rows":sum(reject.values()),"reject_reasons":dict(reject),"row_kinds":dict(kinds),
                    "distinct_provider_keys":len(ccns),"distinct_survey_event_keys":len(events),
                    "events_with_nonmemo_tag":len(event_nonmemo),"events_without_nonmemo_tag":len(events)-len(event_nonmemo),
                    "retained_row_level_records":0,
                    "limits":"Historical source rows and observed tag classifications, not open violations, service needs or verified current operation. No narratives, names, locations, tag values or individual survey or provider identifiers retained in artifacts. Publisher report display count may use different grain."}
    finally:book.close()

def main():
    p=argparse.ArgumentParser();p.add_argument("--source",choices=SOURCES,required=True);p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    with tempfile.TemporaryDirectory(prefix="qcor-provider-") as t:
        path=Path(t)/"source.xlsx";meta=download(a.source,path);result=inspect(path,a.source)
    result.update({"source":meta,"reuse_review":"pending"})
    a.audit.parent.mkdir(parents=True,exist_ok=True)
    with a.audit.open("x") as f:json.dump(result,f,indent=2);f.write("\n")
    print("QCOR_PROVIDER_AUDIT",json.dumps(result),flush=True)
    require(result["mapping_complete"] and result["stored_rows"]>0 and result["rejected_rows"]==0,"source requires further qualification")
if __name__=="__main__":main()
