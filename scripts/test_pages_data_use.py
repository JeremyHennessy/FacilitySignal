"""Check the new capacity source and published aggregates using real static source data."""
import json,os,subprocess,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8099/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"qualified-data-use-browser"
OUT.mkdir(exist_ok=True)
data=json.loads((ROOT/"web/public-directory/long-term-hospital.json").read_text())
evidence=json.loads((ROOT/"research/qualified_data_use_20261126.json").read_text())
provider=next(r for r in data["records"] if r["capacity"])
server=subprocess.Popen(["python","-m","http.server","8099","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            with urlopen(URL,timeout=2):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError("local server unavailable")
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        for width in (390,768,1024,1440):
            page=b.new_page(viewport={"width":width,"height":900})
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(URL+"#capacity?source=long-term-hospital")
            page.get_by_role("columnheader",name="Total beds",exact=True).wait_for()
            assert page.locator(".metrics .metric strong").all_inner_texts()==["311","21,765","305","6"]
            assert page.locator("select[name=source]").input_value()=="long-term-hospital"
            page.screenshot(path=str(OUT/f"{width}-ltch-capacity.png"),full_page=True)
            page.goto(URL+"#capacity?source=long-term-hospital&reported=unknown")
            page.get_by_role("columnheader",name="Total beds",exact=True).wait_for()
            assert page.locator(".metrics .metric strong").all_inner_texts()==["6","—","0","6"]
            page.goto(URL+"#detail?"+urlencode({"source":"long-term-hospital","id":provider["ccn"],"state":provider["state"],"section":"services"}))
            page.get_by_role("heading",name="Reported capacity and service evidence").wait_for()
            assert page.get_by_text("Total beds",exact=True).count()==1
            assert page.get_by_text(f'{int(provider["capacity"]):,}',exact=True).count()>=1
            page.screenshot(path=str(OUT/f"{width}-ltch-profile.png"),full_page=True)
            page.goto(URL+"#advanced?source=long-term-hospital&min=50&run=1")
            page.locator('.advanced-status[data-complete="true"]').wait_for()
            assert page.locator("tbody tr").count()>0
            page.goto(URL+"#services")
            page.get_by_role("heading",name="ASC service provision arrangements").wait_for()
            page.get_by_role("heading",name="Home health reported services").wait_for()
            assert page.get_by_text("4,947",exact=True).count()>=1
            page.locator('[aria-label^="ASC service provision arrangements"]').screenshot(path=str(OUT/f"{width}-asc-arrangements.png"))
            page.goto(URL+"#data-evidence")
            page.get_by_role("heading",name="National field audit coverage").wait_for()
            page.get_by_role("heading",name="Home health general control classification").wait_for()
            page.get_by_role("heading",name="CLIA certificate code distribution").wait_for()
            page.get_by_role("heading",name="Hospital-to-laboratory reference evidence").wait_for()
            page.locator('[aria-label^="Hospital-to-laboratory reference evidence"]').screenshot(path=str(OUT/f"{width}-clia-links.png"))
            assert page.get_by_text("1,433",exact=True).count()>=1
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            assert not errors,errors
            page.close()
        b.close()
    print("QUALIFIED_DATA_USE_BROWSER_PASS",flush=True)
finally:
    server.terminate();server.wait(timeout=5)
