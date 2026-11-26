"""Qualify the publicly downloadable HRSA 340B covered-entity report.

Use the public report control in a current browser session, as HRSA documents.
No login, direct postback replay, shipping address, pharmacy relationships,
contact data, or row-level output. Do not infer current licensure or site identity.
"""
import argparse,hashlib,json,re,sqlite3,tempfile,zipfile
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
import openpyxl
from build_combined import require

URL="https://340bopais.hrsa.gov/Reports/"
HOSTS={"340bopais.hrsa.gov","340bregistration.hrsa.gov"}
MAX_BYTES=350_000_000
MAX_EXPANDED=2_000_000_000
MAX_ROWS=1_000_000
LABEL=re.compile(r"^Covered Entity Daily (?:Report|Export)(?:\s*\(Excel\))?$",re.I)
FIELDS=("340b id","ce id","entity type","participating")
SHEET="covered entities"

def norm(s):return " ".join(str(s or "").split()).casefold()
def official(url):
    p=urlsplit(url)
    return p.scheme=="https" and p.hostname in HOSTS and p.port in (None,443) and not p.username and not p.password
def report_page(url):
    p=urlsplit(url)
    return official(url) and p.path.rstrip("/").casefold()=="/reports"
def download(root):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            context=browser.new_context(accept_downloads=True)
            page=context.new_page()
            res=page.goto(URL,wait_until="domcontentloaded",timeout=60_000)
            require(res is not None and res.ok and report_page(page.url),"public report page inaccessible")
            # The official report may be a button or a link. Require one exact
            # visible label, not a guessed backend endpoint or JSON control.
            choices=[]
            for role in ("button","link"):
                loc=page.get_by_role(role,name=LABEL)
                for i in range(loc.count()):
                    item=loc.nth(i)
                    if item.is_visible():choices.append(item)
            require(len(choices)==1,"covered-entity report control absent or ambiguous")
            with page.expect_download(timeout=180_000) as event:choices[0].click(timeout=15_000)
            item=event.value
            require(official(item.url) or item.url.startswith("blob:https://340bopais.hrsa.gov/"),"unexpected report download origin")
            require(item.failure() is None,"publisher report download failed")
            temp=Path(item.path())
            require(0<temp.stat().st_size<=MAX_BYTES,"download bound")
            require(zipfile.is_zipfile(temp),"publisher file is not XLSX")
            path=root/"covered-entities.xlsx"
            # Move rather than retain a second copy. No path/name from the
            # publisher is used as a filesystem destination.
            import shutil
            shutil.move(temp,path)
            with path.open("rb") as f:digest=hashlib.file_digest(f,"sha256").hexdigest()
            return path,{"url":URL,"bytes":path.stat().st_size,
                         "sha256":digest,
                         "retrieved_at":datetime.now(timezone.utc).isoformat()}
        finally:browser.close()

def participation(v):
    if v is True:return "publisher_true"
    if v is False:return "publisher_false"
    s=norm(v)
    if s in {"true","yes"}:return "publisher_true"
    if s in {"false","no"}:return "publisher_false"
    return "blank" if not s else "unrecognized"
def inspect(path):
    with zipfile.ZipFile(path) as z:
        require(len(z.infolist())<=2000 and sum(x.file_size for x in z.infolist())<=MAX_EXPANDED,"archive bound")
        require("xl/workbook.xml" in z.namelist(),"not XLSX")
    book=openpyxl.load_workbook(path,read_only=True,data_only=True,keep_links=False)
    try:
        candidates=[s for s in book.worksheets if norm(s.title)==SHEET]
        require(len(candidates)==1,"covered entities worksheet absent or ambiguous")
        sheet=candidates[0];sheet.reset_dimensions();it=iter(sheet.iter_rows(values_only=True))
        header=None;ordinal=0
        for ordinal,values in enumerate(it,1):
            require(ordinal<=20,"header not found")
            names=[norm(x) for x in values]
            if all(k in names for k in FIELDS):
                require(len(values)<=150 and all(names.count(k)==1 for k in FIELDS),"ambiguous required header")
                header=values;break
        require(header is not None,"required covered-entity schema absent")
        m={k:[norm(x) for x in header].index(k) for k in FIELDS}
        counts=Counter();types=set();bad=Counter();total=blank=0
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("CREATE TABLE entities(ce TEXT PRIMARY KEY,code TEXT NOT NULL,participation TEXT NOT NULL)")
            for values in it:
                if not any(v is not None and v!="" for v in values):blank+=1;continue
                total+=1;require(total<=MAX_ROWS,"row bound")
                def get(k):
                    i=m[k];return values[i] if i<len(values) else None
                id1=str(get("340b id") or "").strip()
                raw=get("ce id");id2=str(raw or "").strip()
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",id1) or not re.fullmatch(r"[0-9]{1,20}",id2):
                    bad["identifier_shape"]+=1;continue
                code=str(get("entity type") or "").strip().upper()
                if not re.fullmatch(r"[A-Z]{2,6}",code):bad["entity_type_shape"]+=1;continue
                state=participation(get("participating"))
                if state in ("blank","unrecognized"):bad["participation_"+state]+=1;continue
                # Only institutional report identifiers exist transiently.
                n=db.execute("INSERT OR IGNORE INTO entities VALUES(?,?,?)",(id2,id1,state)).rowcount
                if n!=1:bad["duplicate_ce_id"]+=1;continue
                counts[state]+=1;types.add(code)
            db.commit()
            n=db.execute("SELECT count(*) FROM entities").fetchone()[0]
            distinct=db.execute("SELECT count(DISTINCT code) FROM entities").fetchone()[0]
            require(total==n+sum(bad.values()) and n==sum(counts.values()),"row reconciliation")
            require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite integrity")
        return {"source_id":"FS-017","input_rows":total,"stored_rows":n,"rejected_rows":sum(bad.values()),
                "reject_reasons":dict(bad),"blank_rows":blank,"header_row":ordinal,"column_count":len(header),
                "distinct_ce_ids":n,"distinct_340b_ids":distinct,"distinct_entity_type_codes":len(types),
                "participation_counts":dict(counts),"worksheet_count":len(book.worksheets),
                "shipping_and_contract_pharmacy_sheets_parsed":False,"retained_row_level_records":0,
                "limits":"Covered-entity registry records only; no address, contacts, pharmacy, shipping, pricing or provider-level details retained. Participation is publisher-reported, not licensure, compliance or unique physical site. Daily release date not independently pinned; retrieval time and exact workbook hash recorded."}
    finally:book.close()

def main():
    p=argparse.ArgumentParser();p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    with tempfile.TemporaryDirectory(prefix="hrsa-340b-") as d:
        path,meta=download(Path(d));result=inspect(path)
    result.update({"publisher":meta,"reuse_review":"pending","documentation":"https://340bregistration.hrsa.gov/help/CoveredEntity/Reports/DailyReports.htm"})
    with a.audit.open("x") as f:json.dump(result,f,indent=2);f.write("\n")
    print("HRSA_340B_AUDIT",json.dumps(result),flush=True)
    require(result["stored_rows"]>0 and result["rejected_rows"]==0,"covered entity exceptions")
if __name__=="__main__":main()
