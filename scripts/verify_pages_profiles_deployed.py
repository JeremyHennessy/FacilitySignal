"""Verify exact published UI assets and real browser behavior after the Pages push."""
import hashlib,json,os,time
from pathlib import Path
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL="https://jeremyhennessy.github.io/FacilitySignal/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"deployed-profile-evidence"
OUT.mkdir(exist_ok=True)
assets=["index.html","web/pages.js","web/pages.css","web/public-intelligence.json"]
def digest(v):return hashlib.sha256(v).hexdigest()
expected={name:digest((ROOT/name).read_bytes()) for name in assets}
revision=os.environ.get("GITHUB_SHA","local")
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,args=["--no-sandbox"])
    request=p.request.new_context()
    for attempt in range(24):
        actual={}
        for name in assets:
            response=request.get(URL+("" if name=="index.html" else name)+"?rev="+revision,timeout=20000)
            if response.ok:actual[name]=digest(response.body())
        if actual==expected:break
        if attempt==23:raise AssertionError("Deployed asset hashes do not match candidate: "+json.dumps(actual))
        time.sleep(5)
    evidence=json.loads((ROOT/"web/public-intelligence.json").read_text())
    provider=json.loads((ROOT/"web/public-directory/nursing.json").read_text())["records"][0]
    for width in (390,1440):
        page=b.new_page(viewport={"width":width,"height":900})
        errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        for section in evidence["sections"]:
            page.goto(URL+"?rev="+revision+"#"+section["id"])
            page.get_by_role("heading",name=section["title"],exact=True).wait_for()
            page.locator("tbody tr").first.wait_for()
            assert page.locator("#app .table-wrap").count()==len(section["groups"])
        page.goto(URL+"?rev="+revision+"#detail?"+urlencode({"source":"nursing","id":provider["ccn"],"state":provider["state"],"section":"sources"}))
        page.get_by_role("heading",name="Evidence availability for this record").wait_for()
        assert page.get_by_role("navigation",name="Facility evidence sections").count()==1
        page.goto(URL+"?rev="+revision+"#capacity?source=dialysis&state=NY")
        page.locator(".capacity-band").first.wait_for()
        assert page.locator(".capacity-band").count()==6
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
        assert not errors,errors
        page.close()
    request.dispose();b.close()
report={"url":URL,"revision":revision,"asset_sha256":expected,"widths":[390,1440],"checks":["exact deployed assets","all four aggregate research routes","facility evidence sections","capacity distribution","no browser errors"]}
(OUT/"report.json").write_text(json.dumps(report,indent=2)+"\n")
print("LIVE_PROFILE_RELEASE_PASS",json.dumps(report),flush=True)
