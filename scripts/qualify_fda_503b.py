"""FDA 503B registration table aggregate-only qualification.

Do not retain personal contacts, addresses, facility identifiers or individual
inspection outcomes. Do not use reported registration as approval or compliance.
"""
import argparse,hashlib,json,re,sqlite3,urllib.request
from collections import Counter
from contextlib import closing
from datetime import date,datetime,timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from build_combined import require

URL="https://www.fda.gov/drugs/human-drug-compounding/registered-outsourcing-facilities"
MAX_BYTES=5_000_000
def norm(s):return " ".join(s.split()).casefold()
HEAD=["facility","contact","initial registration date","most recent registration date","last inspection","form 483 issued?","recall conducted?","action based on last inspection","intends to compound sterile drugs from bulk substances"]
class Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.tables=[];self.table=None;self.row=None;self.cell=None;self.sup=0;self.text=[]
    def handle_starttag(self,tag,attrs):
        if tag=="table":
            require(self.table is None,"nested table");self.table=[]
        elif tag=="tr" and self.table is not None:self.row=[]
        elif tag in ("td","th") and self.row is not None:
            self.cell=[];self.sup=0
        elif tag=="sup" and self.cell is not None:self.sup+=1
        elif tag in ("br","p","div") and self.cell is not None:self.cell.append(" ")
    def handle_data(self,data):
        if self.cell is not None:
            # Discard contact field immediately, even before constructing rows.
            if len(self.row)!=1 and not self.sup:self.cell.append(data)
            elif len(self.row)==1 and not self.table:self.cell.append(data)
        elif self.table is None:
            self.text.append(data)
    def handle_endtag(self,tag):
        if tag=="sup" and self.sup:self.sup-=1
        elif tag in ("td","th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()));self.cell=None
        elif tag=="tr" and self.row is not None:
            if self.row:self.table.append(self.row)
            self.row=None
        elif tag=="table" and self.table is not None:self.tables.append(self.table);self.table=None
def day(raw):
    v=raw.strip()
    if not re.fullmatch(r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}",v):return None
    try:return datetime.strptime(v,"%m/%d/%Y").date()
    except ValueError:return None
def audit(data):
    p=Parser();p.feed(data.decode("utf-8",errors="strict"));p.close()
    versions=set()
    for m in re.finditer(r"Updated\s+as\s+of\s+(\d{1,2}/\d{1,2}/\d{4})"," ".join(p.text),re.I):
        d=day(m.group(1))
        if d:versions.add(d)
    require(len(versions)==1,"missing/ambiguous publisher update date")
    release=versions.pop()
    candidates=[t for t in p.tables if t and [norm(x) for x in t[0]]==HEAD]
    require(len(candidates)==1,"missing/ambiguous registration table")
    rows=candidates[0][1:];counts=Counter();anomalies=Counter();seen=set();duplicate=0
    require(0<len(rows)<=1000,"table row bound")
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE TABLE registrations(ordinal INTEGER PRIMARY KEY,initial_date TEXT,latest_date TEXT)")
        for i,row in enumerate(rows,1):
            if len(row)!=len(HEAD):anomalies["row_width"]+=1;continue
            name=norm(row[0])
            if not name:anomalies["blank_facility"]+=1;continue
            key=hashlib.sha256(name.encode()).hexdigest()
            if key in seen:duplicate+=1
            seen.add(key)
            initial=day(row[2]);latest=day(row[3])
            if not initial or not latest or not initial<=latest<=release:
                anomalies["registration_date_shape_or_order"]+=1;continue
            db.execute("INSERT INTO registrations VALUES(?,?,?)",(i,initial.isoformat(),latest.isoformat()))
            counts["initial_registration_year_"+str(initial.year)]+=1
        db.commit()
        n=db.execute("SELECT count(*) FROM registrations").fetchone()[0]
        require(n+sum(anomalies.values())==len(rows) and sum(counts.values())==n,"record reconciliation")
        require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite integrity")
    return {"source_id":"FS-077","publisher_updated":release.isoformat(),"input_rows":len(rows),"stored_rows":n,
            "rejected_rows":sum(anomalies.values()),"reject_reasons":dict(anomalies),"duplicate_normalized_labels":duplicate,
            "registration_year_counts":dict(sorted(counts.items())),"columns":len(HEAD),"retained_row_level_records":0,
            "limits":"FDA-listed registration table observations only; distinct labels not verified physical sites. No contacts, addresses, inspection outcomes or row values retained. Registration is not FDA approval or verified current compliance."}
def same_page(url):
    p=urlsplit(url);target=urlsplit(URL)
    return (p.scheme=="https" and p.hostname in {"fda.gov","www.fda.gov"} and
            p.port in (None,443) and not p.username and not p.password and
            p.path.rstrip("/")==target.path and not p.query and not p.fragment)

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        p=urlsplit(newurl)
        safe_path=p.path if p.hostname in {"www.fda.gov","fda.gov"} and re.fullmatch(r"/[A-Za-z0-9/_-]{1,200}",p.path) else "other_or_unverified"
        print("FDA_REDIRECT",json.dumps({"status":code,"official_host":p.hostname in {"www.fda.gov","fda.gov"},"path":safe_path,"query_present":bool(p.query),"same_page":same_page(newurl)}),flush=True)
        require(same_page(newurl),"unexpected redirect")
        return super().redirect_request(req,fp,code,msg,headers,newurl)
def main():
    p=argparse.ArgumentParser();p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    req=urllib.request.Request(URL,headers={"User-Agent":"FacilitySignal institutional source qualification","Accept":"text/html"})
    with urllib.request.build_opener(Redirect()).open(req,timeout=60) as res:
        require(same_page(res.geturl()),"unexpected response URL");data=res.read(MAX_BYTES+1)
    require(0<len(data)<=MAX_BYTES,"page bound")
    result=audit(data)
    result.update({"publisher_url":URL,"html_sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data),"retrieved_at":datetime.now(timezone.utc).isoformat(),"reuse_review":"pending"})
    with a.audit.open("x") as f:json.dump(result,f,indent=2);f.write("\n")
    print("FDA_503B_AUDIT",json.dumps(result),flush=True)
    require(result["stored_rows"]>0 and result["rejected_rows"]==result["duplicate_normalized_labels"]==0,"registration exceptions")
if __name__=="__main__":main()
