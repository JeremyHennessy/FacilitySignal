"""Aggregate-only qualification of eight additional official QCOR reports.

Resolve each workbook link from its publisher page. Source-scoped identifier shape
is not a certification type crosswalk. Never retain survey narratives, site names,
addresses, individual identifiers or facility-level findings in artifacts.
"""
import argparse,hashlib,json,re,sqlite3,tempfile,zipfile
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin,urlsplit
import openpyxl
from scripts.probe_qcor_hospital import request,header_candidate
from scripts.qualify_qcor_provider import map_header,ALIASES
from collect_qcor_hospital import survey_date
from build_combined import require

ROOT="https://qcor.cms.gov/"
SOURCES={
 "cah":("FS-023","CAH_2567_Reports","CAH"),
 "transplant":("FS-024","Transplant_2567_Reports","Transplant"),
 "rhc":("FS-026","RHC_2567_Reports","RHC"),
 "fqhc":("FS-027","FQHC_2567_Reports","FQHC"),
 "prtf":("FS-029","PRTF_2567_Reports","PRTF"),
 "corf":("FS-030","CORF_2567_Reports","CORF"),
 "icf":("FS-031","ICF-IID_2567_Reports","ICF-IID"),
 "hha":("FS-032","HHA_2567_Reports","HHA"),
}
MAX_PAGE=5_000_000
MAX_BYTES=350_000_000
MAX_EXPANDED=2_000_000_000
MAX_ROWS=1_500_000

class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.href=None;self.parts=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=="a":self.href=dict(attrs).get("href");self.parts=[]
    def handle_data(self,data):
        if self.href is not None:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=="a" and self.href is not None:
            self.links.append((self.href," ".join("".join(self.parts).split())))
            self.href=None;self.parts=[]

def resolve_download(html,key):
    _,page,label=SOURCES[key];parser=Links();parser.feed(html)
    pattern=re.compile(r"Download full "+re.escape(label)+r" 2567 dataset\s*\(Excel/XLSX\)",re.I)
    matches=set()
    for href,caption in parser.links:
        if not pattern.fullmatch(caption):continue
        url=urljoin(ROOT+page,href);p=urlsplit(url)
        require(p.scheme=="https" and p.netloc=="qcor.cms.gov" and not p.query and not p.fragment
                and re.fullmatch(r"/download[A-Za-z0-9_-]*2567",p.path,re.I),"unexpected workbook link")
        matches.add(url)
    require(len(matches)==1,"missing or ambiguous official workbook link")
    return matches.pop()

def download(key,path):
    _,page,_=SOURCES[key];page_url=ROOT+page
    with request(page_url,"text/html") as response:
        require(response.geturl()==page_url,"unexpected report redirect")
        html=response.read(MAX_PAGE+1)
        require(0<len(html)<=MAX_PAGE,"report page bound")
    url=resolve_download(html.decode("utf-8",errors="strict"),key)
    h=hashlib.sha256();size=0
    with request(url,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") as res,path.open("xb") as f:
        require(res.geturl()==url,"unexpected download redirect")
        while chunk:=res.read(1024*1024):
            size+=len(chunk);require(size<=MAX_BYTES,"download bound")
            h.update(chunk);f.write(chunk)
        meta={"url":url,"bytes":size,"sha256":h.hexdigest(),"last_modified":res.headers.get("Last-Modified"),
              "etag":res.headers.get("ETag"),"retrieved_at":datetime.now(timezone.utc).isoformat()}
    require(zipfile.is_zipfile(path),"not XLSX")
    with zipfile.ZipFile(path) as z:
        require(len(z.infolist())<=2000 and sum(x.file_size for x in z.infolist())<=MAX_EXPANDED,"archive bound")
        require("xl/workbook.xml" in z.namelist(),"not workbook")
    return meta

def provider_key(value):
    if isinstance(value,int) and not isinstance(value,bool) and 0<=value<=999999:
        return str(value).zfill(6)
    s="" if value is None else str(value).strip().upper()
    # CMS SOM 2779A1, revision 226 (December 6, 2024): additional state
    # codes A0-A9, B0-B9, C0-C9, D0-D9, E1-E3 are documented.
    # Add only the observed letter-first plus five-digit shape. No geography
    # or certification-type inference and no changes to numeric-prefix rules.
    extra_prefixes={a+str(n) for a in "ABCD" for n in range(10)}|{"E1","E2","E3"}
    numeric_prefix=re.fullmatch(r"[0-9]{2}[A-Z0-9][0-9]{3}",s)
    alpha_prefix=len(s)==6 and s[:2] in extra_prefixes and re.fullmatch(r"[0-9]{4}",s[2:])
    require(bool(numeric_prefix or alpha_prefix),"provider_key_shape")
    return s

def classify(values,m,source=None):
    def raw(k):
        i=m[k];return values[i] if i<len(values) else None
    def get(k):
        v=raw(k);return "" if v is None else str(v).strip()
    ccn=provider_key(raw("ccn"))
    event=get("event").upper()
    require(len(event)<=32 and re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*",event) is not None,"event_key_shape")
    try:day=survey_date(raw("date"))
    except ValueError:raise ValueError("survey_date_shape") from None
    tag=get("tag").upper();kind=get("kind").casefold()
    # The official ICF-IID reports visibly use KS and KA plus three digits.
    # Only permit this exact additional shape in ICF-IID; no other source
    # or tag family is changed and no regulatory meaning is inferred.
    valid_tag=not tag or re.fullmatch(r"[A-Z][0-9]{4}",tag) is not None or (
        source=="icf" and re.fullmatch(r"(?:KS|KA)[0-9]{3}",tag) is not None)
    require(valid_tag,"tag_key_shape")
    require(bool(tag) or not kind,"missing_tag_with_type")
    state="memo" if kind=="memo" or re.fullmatch(r"[A-Z]0000",tag) else "nonmemo_tag" if tag else "no_tag_reported"
    return ccn,event,day,state

def inspect(path,key):
    book=openpyxl.load_workbook(path,read_only=True,data_only=True,keep_links=False)
    try:
        require(len(book.worksheets)==1,"unexpected sheet count")
        sheet=book.worksheets[0];sheet.reset_dimensions()
        rows=iter(sheet.iter_rows(values_only=True));header=tuple(next(rows,()))
        require(header_candidate(header),"unrecognized header")
        require(all(isinstance(x,str) and 0<len(x)<=150 and "\n" not in x and "\r" not in x for x in header),"header shape")
        m=map_header(header);ready=set(m)==set(ALIASES)
        kinds=Counter();reject=Counter();tag_shapes=Counter();total=blank=0
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE TABLE survey(ordinal INTEGER PRIMARY KEY,ccn TEXT NOT NULL,event TEXT NOT NULL,day TEXT NOT NULL,kind TEXT NOT NULL)")
            batch=[]
            for ordinal,values in enumerate(rows,2):
                require(ordinal<=MAX_ROWS+1,"row bound")
                # Check only whether cells are empty; never project narratives.
                if not any(v is not None and v!="" for v in values):blank+=1;continue
                total+=1
                if not ready:continue
                if len(values)>len(header):reject["extra_columns"]+=1;continue
                try:c,e,d,k=classify(values,m,key)
                except ValueError as exc:
                    reject[str(exc)]+=1
                    if str(exc)=="tag_key_shape":
                        i=m["tag"];v=values[i] if i<len(values) else None
                        raw="" if v is None else str(v).strip().upper()
                        shape=("".join("A" if "A"<=c<="Z" else "9" if "0"<=c<="9" else "S" if c.isspace() else "P" for c in raw)
                               if len(raw)<=24 else "over_24")
                        tag_shapes[shape]+=1
                    continue
                batch.append((ordinal,c,e,d,k));kinds[k]+=1
                if len(batch)>=5000:
                    db.executemany("INSERT INTO survey VALUES(?,?,?,?,?)",batch);batch.clear()
            if batch:db.executemany("INSERT INTO survey VALUES(?,?,?,?,?)",batch)
            db.commit()
            stored=db.execute("SELECT count(*) FROM survey").fetchone()[0]
            events=db.execute("SELECT count(*) FROM (SELECT DISTINCT ccn,event,day FROM survey)").fetchone()[0]
            providers=db.execute("SELECT count(DISTINCT ccn) FROM survey").fetchone()[0]
            with_tag=db.execute("SELECT count(*) FROM (SELECT DISTINCT ccn,event,day FROM survey WHERE kind='nonmemo_tag')").fetchone()[0]
            require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite integrity")
            if ready:require(total==stored+sum(reject.values()) and stored==sum(kinds.values()),"row reconciliation")
            return {"source_id":SOURCES[key][0],"report_url":ROOT+SOURCES[key][1],"header":list(header),"columns":len(header),
                    "field_mapping":{k:header[i] for k,i in m.items()},"mapping_complete":ready,
                    "input_rows":total,"blank_rows":blank,"stored_rows":stored,"rejected_rows":sum(reject.values()),
                    "reject_reasons":dict(reject),"rejected_tag_shapes":dict(tag_shapes),"row_kinds":dict(kinds),"distinct_provider_keys":providers,
                    "distinct_survey_event_keys":events,"events_with_nonmemo_tag":with_tag,
                    "events_without_nonmemo_tag":events-with_tag,"retained_row_level_records":0,
                    "limits":"Source-scoped historical observations, not unique sites, current compliance or purchasing intent. Provider key shape only, not confirmed provider type. No source narratives or individual identifiers retained. No independent publisher workbook-count comparison available."}
    finally:book.close()

def main():
    p=argparse.ArgumentParser();p.add_argument("--source",choices=SOURCES,required=True);p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    with tempfile.TemporaryDirectory(prefix="qcor-expansion-") as t:
        path=Path(t)/"source.xlsx";meta=download(a.source,path);result=inspect(path,a.source)
    result.update({"source":meta,"reuse_review":"pending"})
    a.audit.parent.mkdir(parents=True,exist_ok=True)
    with a.audit.open("x") as f:json.dump(result,f,indent=2);f.write("\n")
    print("QCOR_EXPANSION_AUDIT",json.dumps(result),flush=True)
    require(result["mapping_complete"] and result["stored_rows"]>0 and result["rejected_rows"]==0,"source anomalies require review")
if __name__=="__main__":main()
