"""Test compact mobile navigation and profile research on existing public records."""
import json,os,subprocess,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8099/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"mobile-evidence";OUT.mkdir(exist_ok=True)
provider=json.loads((ROOT/"web/public-directory/nursing.json").read_text())["records"][0]
server=subprocess.Popen(["python","-m","http.server","8099","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            with urlopen(URL,timeout=2):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError("local HTTP unavailable")
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        for width in (390,768,1024,1440):
            page=b.new_page(viewport={"width":width,"height":900})
            errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(URL)
            page.get_by_role("heading",name="National overview").wait_for()
            if width<=720:
                nav=page.locator("aside nav");assert nav.evaluate("(e)=>e.scrollWidth>e.clientWidth&&getComputedStyle(e).flexWrap==='nowrap'")
                assert page.locator("#mobile-route").is_visible()
                page.locator("#mobile-route").select_option("#procurement")
            else:
                assert not page.locator("#mobile-route").is_visible()
                page.get_by_role("link",name="Procurement research",exact=True).first.click()
            page.get_by_role("heading",name="Commercial evidence classifications").wait_for()
            assert page.get_by_text("No confirmed procurement opportunities",exact=False).count()==1
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.screenshot(path=str(OUT/f"{width}-procurement.png"),full_page=True)
            page.goto(URL+"#detail?"+urlencode({"source":"nursing","id":provider["ccn"],"state":provider["state"]}))
            page.get_by_role("heading",name="Continue this research").wait_for()
            page.locator(".profile-research-actions").screenshot(path=str(OUT/f"{width}-profile-actions.png"))
            page.get_by_role("link",name="All provider records in reported city").click()
            page.locator('.advanced-status[data-complete="true"]').wait_for()
            assert page.locator("input[name=q]").input_value()==provider["city"]
            assert page.locator("select[name=field]").input_value()=="city"
            page.goto(URL+"#ownership");page.get_by_role("heading",name="Ownership evidence coverage").wait_for()
            assert page.locator(".metrics .metric").count()==6
            if width<=720:
                assert page.locator("#mobile-route").input_value()=="#ownership"
                assert page.locator("#app .table-wrap").first.evaluate("(e)=>e.scrollWidth>e.clientWidth")
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            assert not errors,errors
            page.screenshot(path=str(OUT/f"{width}-ownership.png"),full_page=True)
            page.close()
        b.close()
    print("MOBILE_EVIDENCE_BROWSER_PASS",flush=True)
finally:server.terminate();server.wait(timeout=5)
