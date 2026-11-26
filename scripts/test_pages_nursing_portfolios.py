"""Exercise nursing aggregate research and safe provider pathways at mobile and desktop widths."""
import json, os, subprocess, time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8098/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"nursing-portfolio-evidence"
OUT.mkdir(exist_ok=True)
groups={g["id"]:g for s in json.loads((ROOT/"web/public-intelligence.json").read_text())["sections"] for g in s["groups"]}
ids=["nursing-chain-coverage","nursing-affiliation-corroboration","nursing-inspection-disputes"]
server=subprocess.Popen(["python","-m","http.server","8098","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            with urlopen(URL,timeout=2):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError("HTTP unavailable")
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        for width in (390,768,1024,1440):
            page=browser.new_page(viewport={"width":width,"height":900})
            errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(URL+"#nursing-portfolios")
            page.get_by_role("heading",name="Nursing portfolio research",exact=True).wait_for()
            page.locator("#app .intelligence-table").last.wait_for()
            tables=page.locator("#app .intelligence-table")
            assert tables.count()==3
            for i,ident in enumerate(ids):
                expected=[[f"{x:,}" if type(x) is int else x for x in row] for row in groups[ident]["rows"]]
                assert [r.locator("td").all_inner_texts() for r in tables.nth(i).locator("tbody tr").all()]==expected
            assert "Named chain memberships are not published" in page.locator("#app").inner_text()
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.screenshot(path=str(OUT/f"{width}-nursing-portfolios.png"),full_page=True)
            for pathway,fragment in [("facilities","#facilities?source=nursing&state=NY"),("capacity","#capacity?source=nursing&state=NY"),("nursing-health","#citations?source=nursing-health&state=NY"),("nursing-fire","#citations?source=nursing-fire&state=NY")]:
                page.goto(URL+"#nursing-portfolios")
                page.locator("select[name=state]").select_option("NY")
                page.locator("select[name=path]").select_option(pathway)
                page.get_by_role("button",name="Open research").click()
                assert page.url.endswith(fragment),page.url
                page.go_back()
                page.get_by_role("heading",name="Nursing portfolio research",exact=True).wait_for()
            assert not errors,errors
            page.close()
        browser.close()
    print("NURSING_PORTFOLIO_BROWSER_PASS",flush=True)
finally:
    server.terminate();server.wait(timeout=5)
