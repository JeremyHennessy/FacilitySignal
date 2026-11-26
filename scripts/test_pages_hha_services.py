"""Exercise actual HHA projection, AND filter, CSV and source-linked profiles."""
import csv,io,json,os,subprocess,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8097/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"hha-service-evidence";OUT.mkdir(exist_ok=True)
P=json.loads((ROOT/"web/hha-service-evidence.json").read_text())
OBS=P["records"];FIELDS=P["fields"]
ROWS=json.loads((ROOT/"web/public-directory/home-health.json").read_text())["records"]
def key(r):return r["state"]+":"+r["ccn"]
def actual(r):return OBS[key(r)]
LABEL={"yes":"Reported yes","no":"Reported no","dash_marker":"Unknown (source dash)"}
fixture=next(r for r in ROWS if actual(r)["Nursing Care"]=="dash_marker")
server=subprocess.Popen(["python","-m","http.server","8097","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            with urlopen(URL,timeout=2):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError("HTTP unavailable")
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        for width in (390,768,1024,1440):
            page=b.new_page(viewport={"width":width,"height":900},accept_downloads=True)
            errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
            def search(**params):
                page.goto(URL+"#hha-services?"+urlencode(params))
                page.locator(".hha-status[data-ready=true]").wait_for()
                return int(page.locator(".hha-status").get_attribute("data-total"))
            assert search()==12409
            for field in FIELDS:
                for state in ("yes","no","dash_marker"):
                    expected=sum(v[field]==state for v in OBS.values())
                    assert search(field=field,evidence=state)==expected
            expected=sum(r["state"]=="NY" and actual(r)["Nursing Care"]=="yes" and actual(r)["Physical Therapy"]=="yes" for r in ROWS)
            assert search(state="NY",field="Nursing Care",evidence="yes",required="Physical Therapy")==expected
            page.locator('input[name=required][value="Occupational Therapy"]').check()
            page.get_by_role("button",name="Apply service filters").click()
            page.locator(".hha-status[data-ready=true]").wait_for()
            expected2=sum(r["state"]=="NY" and all(actual(r)[x]=="yes" for x in ("Nursing Care","Physical Therapy","Occupational Therapy")) for r in ROWS)
            assert int(page.locator(".hha-status").get_attribute("data-total"))==expected2
            assert page.locator("tbody tr").count()==min(25,expected2)
            with page.expect_download() as info:page.get_by_role("button",name="Export current page (CSV)").click()
            exported=list(csv.DictReader(io.StringIO(info.value.path().read_text())))
            assert len(exported)==min(25,expected2)
            assert all(r["state"]=="NY" and all(r["Offers "+f+" Services"]=="yes" for f in ("Nursing Care","Physical Therapy","Occupational Therapy")) for r in exported)
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            assert page.locator(".hha-required label").evaluate_all("(els)=>els.every(e=>getComputedStyle(e).flexDirection==='row'&&e.querySelector('input').getBoundingClientRect().width>=15)")
            assert page.get_by_text("Scroll horizontally to see all six service columns",exact=False).is_visible()
            page.locator(".hha-service-form").screenshot(path=str(OUT/f"{width}-filters.png"))
            page.locator(".hha-results").screenshot(path=str(OUT/f"{width}-results.png"))
            page.locator(".hha-results tbody a").first.click()
            page.locator(".hha-profile[data-evidence=qualified]").wait_for()
            assert page.get_by_role("link",name="Back to results",exact=True).count()==1
            page.get_by_role("link",name="Back to results",exact=True).click()
            page.locator(".hha-status[data-ready=true]").wait_for()
            assert int(page.locator(".hha-status").get_attribute("data-total"))==expected2
            page.goto(URL+"#detail?"+urlencode({"source":"home-health","id":fixture["ccn"],"state":fixture["state"],"section":"services"}))
            page.locator(".hha-profile[data-evidence=qualified]").wait_for()
            for f,value in actual(fixture).items():assert page.locator(f'.hha-profile [data-field="{f}"] dd').inner_text()==LABEL[value]
            page.locator(".hha-profile").screenshot(path=str(OUT/f"{width}-profile.png"))
            page.route("**/web/hha-service-evidence.json?*",lambda route:route.fulfill(status=200,content_type="application/json",body="{}"))
            page.goto(URL+"#hha-services")
            page.get_by_text("Evidence checksum mismatch",exact=False).wait_for()
            assert page.locator(".hha-results").count()==0 and not errors
            page.close()
        b.close()
    print("HHA_SERVICE_BROWSER_PASS",flush=True)
finally:server.terminate();server.wait(timeout=5)
