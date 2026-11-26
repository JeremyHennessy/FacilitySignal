"""Bounded HRSA public JSON-report qualification via documented UI automation.

One fresh anonymous session and one report-button click. No recorded postback,
login, endpoint guessing or access-control bypass. Parse top-level covered entity
fields only; do not materialize nested address or pharmacy records.
"""
import argparse,hashlib,json,re,sqlite3,tempfile
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from build_combined import require
URL="https://340bopais.hrsa.gov/Reports/"
LABEL="Covered Entity Daily Export (JSON)"
HOSTS={"340bopais.hrsa.gov","340bregistration.hrsa.gov"}
MAX_BYTES=350_000_000
MAX_ROWS=1_000_000
REQUIRED={"340bid","ceid","entitytype","participating"}
def norm(s):return re.sub(r"[^a-z0-9]","",str(s).casefold())
def official(url):
    p=urlsplit(url)
    return p.scheme=="https" and p.hostname in HOSTS and p.port in (None,443) and not p.username and not p.password
def report_page(url):
    return official(url) and urlsplit(url).path.rstrip("/").casefold()=="/reports"

def fetch(root,diagnostic):
    from playwright.sync_api import sync_playwright,TimeoutError as PlaywrightTimeout
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        try:
            context=browser.new_context(accept_downloads=True)
            page=context.new_page()
            status=Counter()
            def response_event(res):
                if official(res.url):
                    mime=res.headers.get("content-type","").split(";")[0].lower()
                    kind=mime if mime in {"application/json","application/octet-stream","text/html","application/zip","text/plain"} else "other"
                    status[f"{res.request.method}:{res.status}:{kind}"]+=1
            page.on("response",response_event)
            try:
                res=page.goto(URL,wait_until="domcontentloaded",timeout=60_000)
                diagnostic["landing_status"]=res.status if res else None
                require(res is not None and res.ok and report_page(page.url),"public report page unavailable")
                matches=[]
                for role in ("button","link"):
                    loc=page.get_by_role(role,name=LABEL,exact=True)
                    for i in range(loc.count()):
                        if loc.nth(i).is_visible():matches.append(loc.nth(i))
                diagnostic["visible_report_controls"]=len(matches)
                require(len(matches)==1,"JSON report control absent or ambiguous")
                require(matches[0].is_enabled(),"report control disabled")
                with page.expect_download(timeout=180_000) as event:
                    matches[0].click(timeout=15_000)
                item=event.value
                require(official(item.url) or item.url.startswith("blob:https://340bopais.hrsa.gov/"),"unexpected report download origin")
                require(item.failure() is None,"download failed")
                path=root/"report.json"
                item.save_as(path)
                require(0<path.stat().st_size<=MAX_BYTES,"download size bound")
                with path.open("rb") as f:digest=hashlib.file_digest(f,"sha256").hexdigest()
                return path,{"url":URL,"format":"json","bytes":path.stat().st_size,"sha256":digest,"retrieved_at":datetime.now(timezone.utc).isoformat()}
            except PlaywrightTimeout:
                raise ValueError("public report download timed out") from None
            finally:
                diagnostic["official_response_classes"]=dict(status)
        finally:browser.close()

def scan(path):
    import ijson
    # Recognize only the official documented top-level covered-entity record
    # fields. Unknown wrappers are reported as structural failure, not guessed.
    # ijson event parsing never constructs nested maps or arrays of row values.
    counts=Counter();bad=Counter();keys=set();rows=0;current=None;schema=Counter()
    with path.open("rb") as f,closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE TABLE entities(ce TEXT PRIMARY KEY)")
        for prefix,event,value in ijson.parse(f):
            if prefix=="" and event=="start_array":schema["root_array"]+=1
            elif prefix=="" and event=="start_map":schema["root_object"]+=1
            if prefix=="item" and event=="start_map":
                require(current is None,"nested record boundary");current={}
            elif current is not None and prefix.startswith("item.") and prefix.count(".")==1 and event in ("string","number","boolean","null"):
                k=norm(prefix.split(".",1)[1])
                if k in REQUIRED:
                    if k in current:current["_duplicate"]=True
                    current[k]=value
            elif prefix=="item" and event=="end_map":
                rows+=1;require(rows<=MAX_ROWS,"row bound")
                r=current;current=None
                if r.get("_duplicate") or not REQUIRED<=r.keys():bad["required_field_absent_or_duplicate"]+=1;continue
                ce=str(r["ceid"] or "").strip();id1=str(r["340bid"] or "").strip();typ=str(r["entitytype"] or "").strip().upper()
                if not re.fullmatch(r"[0-9]{1,20}",ce) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",id1):bad["identifier_shape"]+=1;continue
                if not re.fullmatch(r"[A-Z]{2,6}",typ):bad["entity_type_shape"]+=1;continue
                p=r["participating"]
                if type(p) is not bool:bad["participation_not_boolean"]+=1;continue
                if db.execute("INSERT OR IGNORE INTO entities VALUES(?)",(ce,)).rowcount!=1:bad["duplicate_ce_id"]+=1;continue
                counts["publisher_true" if p else "publisher_false"]+=1;keys.add(typ)
        require(current is None,"unclosed record")
        n=db.execute("SELECT count(*) FROM entities").fetchone()[0]
        require(rows==n+sum(bad.values()) and n==sum(counts.values()),"row reconciliation")
    return {"input_rows":rows,"stored_rows":n,"rejected_rows":sum(bad.values()),"reject_reasons":dict(bad),"root_structure":dict(schema),"participation_counts":dict(counts),"distinct_entity_type_codes":len(keys),"retained_row_level_records":0}

def main():
    p=argparse.ArgumentParser();p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    diag={};meta=None;result={};failure=None
    with tempfile.TemporaryDirectory(prefix="hrsa-json-") as d:
        try:
            path,meta=fetch(Path(d),diag)
            result=scan(path)
            require(result["root_structure"]=={"root_array":1} and result["stored_rows"]>0 and result["rejected_rows"]==0,"source shape or record exceptions")
        except Exception as e:
            reasons={"public report page unavailable","JSON report control absent or ambiguous","report control disabled","unexpected report download origin","download failed","download size bound","public report download timed out","source shape or record exceptions","row bound","row reconciliation","nested record boundary","unclosed record"}
            failure={"type":type(e).__name__,"reason":str(e) if str(e) in reasons else "unclassified_failure"}
    out={"source_id":"FS-017","publisher":meta,"diagnostic":diag,"result":result,"failure":failure,"retained_row_level_records":0,"reuse_review":"pending","limits":"Fresh public UI session only. No nested data or source rows retained, no current licensing or property identity inference. If unsuccessful, do not repeat unattended."}
    with a.audit.open("x") as f:json.dump(out,f,indent=2);f.write("\n")
    print("HRSA_340B_JSON_AUDIT",json.dumps(out),flush=True)
    require(failure is None,"JSON report qualification incomplete")
if __name__=="__main__":main()
