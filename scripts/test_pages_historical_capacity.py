"""Real Chromium validation of exact historical PUF capacity profiles.

Same ordinary URL for live verification; use local mode for candidate. Verify
actual browser-loaded assets, source payloads and directory pins, then inspect
screenshots before release completion. No private data or Azure credentials.
"""
import argparse,hashlib,json,os,subprocess,time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"historical-capacity-profile-evidence";OUT.mkdir(exist_ok=True)
PUBLIC="https://jeremyhennessy.github.io/FacilitySignal/"
PINS=json.loads((ROOT/"research/hcris_capacity_candidate_receipts_20261126.json").read_text())["forms"]
def digest(b):return hashlib.sha256(b).hexdigest()
def read(name):return json.loads((ROOT/name).read_text())
def hashfile(name):return digest((ROOT/name).read_bytes())
ASSETS={k:hashfile(k) for k in ("index.html","web/pages.js","web/pages.css")}
DATA={f:read("web/hcris-capacity/"+f+".json")["records"] for f in ("hospital","snf")}
SOURCE={"hospital":"hospital","snf":"nursing"}
DIRECTORY={f:read("web/public-directory/"+SOURCE[f]+".json")["records"] for f in DATA}
def exact_records(form,r):
    return sorted([v for v in DATA[form] if (v["ccn"],v["state"])==(r["ccn"],r["state"])],key=lambda v:(v["period_begin"],v["period_end"],v["report_key"]),reverse=True)
def samples(form):
    keys=Counter((r["ccn"],r["state"]) for r in DATA[form])
    directory={(r["ccn"],r["state"]):r for r in DIRECTORY[form]}
    missing=next(r for r in DATA[form] if r["measures"]["available_beds_at_period_end"] is None)
    multiple=next(k for k,n in keys.items() if n>1)
    single=next(k for k,n in keys.items() if n==1 and all(v is not None for v in exact_records(form,directory[k])[0]["measures"].values()))
    unlinked=next(k for k in directory if k not in keys and sum(r["ccn"]==k[0] for r in DIRECTORY[form])==1)
    return [("qualified",directory[single]),("multiple",directory[multiple]),("missing",directory[(missing["ccn"],missing["state"])]),("unlinked",directory[unlinked])]
def route(form,r,section=None):
    params={"source":SOURCE[form],"id":r["ccn"],"state":r["state"]}
    if section:params["section"]=section
    return "#detail?"+urlencode(params)
def check_response(responses,url,expected):
    matched=[r for r in responses if r.url==url and r.ok]
    assert matched and digest(matched[-1].body())==expected,"Missing/stale browser response "+url
def check_entry(page,base,utm,responses):
    responses.clear()
    page.goto(base+utm+"#overview",wait_until="domcontentloaded")
    page.get_by_role("heading",name="National overview",exact=True).wait_for()
    check_response(responses,base+utm,ASSETS["index.html"])
    for path in ("web/pages.js","web/pages.css"):
        check_response(responses,base+path+"?v="+ASSETS[path][:16],ASSETS[path])
def verify_panel(page,form,r,kind):
    section=page.locator(".historical-capacity-profile")
    section.wait_for()
    assert section.get_attribute("data-evidence")==("unlinked" if kind=="unlinked" else "qualified")
    expected=exact_records(form,r)
    assert int(section.get_attribute("data-reports"))==len(expected)
    assert section.locator(".historical-capacity-report").count()==len(expected)
    if not expected:
        assert "does not establish zero historical capacity" in section.inner_text()
    for rec in expected:
        card=section.locator('[data-report-key="'+rec["report_key"]+'"]')
        assert card.count()==1
        assert card.get_by_role("heading",name="Fiscal period "+rec["period_begin"]+" – "+rec["period_end"],exact=True).count()==1
        for field,val in rec["measures"].items():
            cell=card.locator('[data-field="'+field+'"]')
            assert cell.locator("dd").inner_text()==("Not reported" if val is None else f"{val:,}")
            assert cell.get_attribute("data-state")==("missing" if val is None else "reported_zero" if val==0 else "reported_positive")
    assert "not inferred from these reports" in section.inner_text()
    assert section.get_by_role("link",name="Official CMS cost-report data").get_attribute("href").startswith("https://data.cms.gov/")
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    return section
def run(base,local):
    report={"scope":"local candidate" if local else "ordinary public URL","commit":os.environ.get("GITHUB_SHA","local"),"screens":[],"assets":ASSETS}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        for width in (390,768,1024,1440):
            ctx=browser.new_context(viewport={"width":width,"height":900})
            page=ctx.new_page();responses=[];errors=[]
            page.on("response",lambda r:responses.append(r));page.on("pageerror",lambda e:errors.append(str(e)))
            check_entry(page,base,"",responses)
            for form in ("hospital","snf"):
                pin=PINS[form];data_path="web/hcris-capacity/"+form+".json?v="+pin["ephemeral_candidate_sha256"][:16]
                directory_path="web/public-directory/"+SOURCE[form]+".json"
                for kind,r in samples(form):
                    responses.clear()
                    page.goto(base+route(form,r))
                    page.get_by_role("link",name="Historical FY2024 cost-report capacity",exact=True).click()
                    panel=verify_panel(page,form,r,kind)
                    check_response(responses,base+data_path,pin["ephemeral_candidate_sha256"])
                    check_response(responses,base+directory_path,pin["directory"]["sha256"])
                    file=f"{width}-{form}-{kind}.png";page.screenshot(path=str(OUT/file),full_page=True)
                    report["screens"].append(file)
                    if kind=="qualified":
                        page.reload();verify_panel(page,form,r,kind)
                        page.get_by_role("link",name="Sources & coverage",exact=True).click()
                        page.get_by_text("FY2024 selected CMS report subset; check exact record",exact=True).wait_for()
                        page.go_back();verify_panel(page,form,r,kind)
                if local:
                    # Actual corrupted payload and failed fetch must not surface any values.
                    r=samples(form)[0][1]
                    page.route("**/web/hcris-capacity/"+form+".json?*",lambda route:route.fulfill(status=200,content_type="application/json",body='{"version":1,"records":[]}'))
                    page.goto(base+route(form,r,"services"))
                    section=page.locator(".historical-capacity-profile[data-evidence=unavailable]");section.wait_for()
                    assert section.locator(".historical-capacity-report").count()==0
                    assert "No values inferred" in section.inner_text()
                    page.unroute("**/web/hcris-capacity/"+form+".json?*")
                    page.route("**/web/hcris-capacity/"+form+".json?*",lambda route:route.abort())
                    page.goto(base+route(form,r,"services"))
                    section=page.locator(".historical-capacity-profile[data-evidence=unavailable]");section.wait_for()
                    assert section.locator(".historical-capacity-report").count()==0
                    page.unroute("**/web/hcris-capacity/"+form+".json?*")
            check_entry(page,base,"?utm_source=chatgpt.com",responses)
            r=samples("hospital")[0][1];responses.clear()
            page.goto(base+"?utm_source=chatgpt.com"+route("hospital",r,"services"));verify_panel(page,"hospital",r,"qualified")
            check_response(responses,base+"web/hcris-capacity/hospital.json?v="+PINS["hospital"]["ephemeral_candidate_sha256"][:16],PINS["hospital"]["ephemeral_candidate_sha256"])
            page.reload();verify_panel(page,"hospital",r,"qualified")
            assert not errors,errors
            ctx.close()
        browser.close()
    (OUT/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("HISTORICAL_CAPACITY_PROFILE_BROWSER_PASS",json.dumps({"scope":report["scope"],"screens":len(report["screens"]),"assets":ASSETS}),flush=True)
def main():
    a=argparse.ArgumentParser();a.add_argument("--local",action="store_true");p=a.parse_args()
    if not p.local:run(PUBLIC,False);return
    base="http://127.0.0.1:8113/"
    server=subprocess.Popen(["python","-m","http.server","8113","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with urlopen(base,timeout=2):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError("local HTTP unavailable")
        run(base,True)
    finally:server.terminate();server.wait(timeout=5)
if __name__=="__main__":main()
