"""Verify public aggregate research routes and prior directory behavior in Chromium."""
import json,os,subprocess,time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8095/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"intelligence-evidence"
OUT.mkdir(exist_ok=True)
evidence=json.loads((ROOT/"web/public-intelligence.json").read_text())
server=subprocess.Popen(["python","-m","http.server","8095","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            with urlopen(URL,timeout=2):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError("local HTTP unavailable")
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        checked=[]
        for width in (390,768,1024,1440):
            page=b.new_page(viewport={"width":width,"height":900})
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(URL)
            page.get_by_text("48,004",exact=True).wait_for()
            for section in evidence["sections"]:
                start=time.perf_counter()
                page.locator("nav a[href='#"+section["id"]+"']").click()
                page.get_by_role("heading",name=section["title"],exact=True).wait_for()
                page.locator("tbody tr").first.wait_for()
                tables=page.locator("#app .table-wrap")
                assert tables.count()==len(section["groups"])
                for i,g in enumerate(section["groups"]):
                    actual=[r.locator("td").all_inner_texts() for r in tables.nth(i).locator("tbody tr").all()]
                    expected=[["—" if v is None else f"{v:,}" if type(v) is int else v for v in row] for row in g["rows"]]
                    assert actual==expected,(section["id"],i,actual,expected)
                    assert page.get_by_role("link",name="Qualification run "+str(g["run"]),exact=True).count()>=1
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1"),(width,section["id"])
                assert not errors,errors
                page.screenshot(path=str(OUT/f"{width}-{section['id']}.png"),full_page=True)
                checked.append({"width":width,"section":section["id"],"render_ms":round((time.perf_counter()-start)*1000,1)})
            page.go_back()
            page.get_by_role("heading",name="Equipment & environmental research",exact=True).wait_for()
            page.goto(URL+"#services")
            page.get_by_role("heading",name="Surgical and dialysis capability evidence").wait_for()
            page.get_by_role("link",name="Search reported public capacity").click()
            page.get_by_role("columnheader",name="Certified beds",exact=True).wait_for()
            page.close()
        (OUT/"report.json").write_text(json.dumps({"aggregate_only":True,"checks":checked},indent=2))
        print("PUBLIC_INTELLIGENCE_BROWSER_PASS",json.dumps(checked),flush=True)
        b.close()
finally:
    server.terminate()
    server.wait(timeout=5)
