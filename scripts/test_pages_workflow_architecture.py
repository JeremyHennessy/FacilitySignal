"""Qualify the task-first home, grouped navigation and exact-source facility comparison."""
import json,os,subprocess,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
from pages_navigation import open_workspace
ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8101/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"workflow-architecture-evidence";OUT.mkdir(exist_ok=True)
def shard(k):return json.loads((ROOT/"web/public-directory"/(k+".json")).read_text())["records"]
nursing=shard("nursing");dialysis=shard("dialysis")
chosen=[("nursing",nursing[0]),("dialysis",dialysis[0]),("nursing",nursing[1])]
def citation(key,r):
    found=[c for c in shard(key) if c["ccn"]==r["ccn"] and c["state"]==r["state"]]
    return f'{found[0]["citation_rows"]:,} historical rows' if len(found)==1 else ("Multiple matching source records" if found else "No matching source record")+" (not zero)"
server=subprocess.Popen(["python","-m","http.server","8101","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            with urlopen(URL,timeout=2):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError("HTTP unavailable")
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        for width in (390,768,1024,1440):
            ctx=b.new_context(viewport={"width":width,"height":900});page=ctx.new_page()
            errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(URL)
            page.get_by_text("48,004",exact=True).wait_for()
            assert page.locator(".home-workflow").count()==4
            assert page.locator("nav[aria-label='Primary navigation'] a").count()==23
            assert page.locator("#mobile-route option").count()==23
            assert page.locator("nav .nav-group[open]").count()==0
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.screenshot(path=str(OUT/f"{width}-home.png"),full_page=True)
            f=page.locator(".home-discovery-form")
            f.locator("select[name=source]").select_option("hospital")
            f.locator("select[name=state]").select_option("NY")
            f.locator("button").click();page.locator('.advanced-status[data-complete="true"]').wait_for()
            assert page.locator("select[name=source]").input_value()=="hospital"
            assert page.locator("select[name=state]").input_value()=="NY"
            page.go_back();page.locator(".home-discovery-form").wait_for()
            open_workspace(page,"procurement");page.locator(".procurement-pilot[data-qualified=true]").wait_for()
            assert page.locator("nav a[aria-current=page]").get_attribute("href")=="#procurement"
            assert page.locator("nav .nav-group[open]").count()==1
            assert page.locator("#mobile-route").input_value()=="#procurement"
            page.screenshot(path=str(OUT/f"{width}-navigation.png"))
            for source,r in chosen:
                page.goto(URL+"#detail?"+urlencode({"source":source,"id":r["ccn"],"state":r["state"]}))
                page.get_by_role("button",name="Save to research portfolio").click()
            page.get_by_role("link",name="Open saved portfolio").click()
            page.locator(".portfolio-count").wait_for()
            assert "3 saved source records" in page.locator(".portfolio-count").inner_text()
            check=page.locator(".portfolio-provider-cell input")
            check.nth(0).check();assert page.get_by_role("button",name="Compare selected (1 / 4)").is_disabled()
            check.nth(1).check();check.nth(2).check()
            page.get_by_role("button",name="Compare selected (3 / 4)").click()
            page.locator(".comparison-table").wait_for()
            assert "3 exact published records resolved" in page.locator(".comparison-status").inner_text()
            rows={c[0]:c[1:] for c in [tr.locator("td").all_inner_texts() for tr in page.locator(".comparison-table tbody tr").all()]}
            assert rows["Source identifier"]==[r["ccn"] for _,r in chosen]
            assert rows["Provider category"]==["Nursing homes","Dialysis facilities","Nursing homes"]
            for domain in ("health","fire"):
                assert rows["Nursing "+domain+" citation evidence"]==[citation("nursing-"+domain,chosen[0][1]),"Not applicable to this source",citation("nursing-"+domain,chosen[2][1])]
            for val,(source,r) in zip(rows["Reported capacity"],chosen):
                assert ("certified beds" if source=="nursing" else "dialysis stations") in val or val=="Not reported / nonnumeric"
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.screenshot(path=str(OUT/f"{width}-comparison.png"),full_page=True)
            page.reload();page.locator(".comparison-table").wait_for()
            page.go_back();page.locator(".portfolio-count").wait_for()
            page.goto(URL+"#compare?records=invalid")
            page.get_by_text("Select 2–4 distinct records from your saved portfolio.",exact=True).wait_for()
            assert not errors,errors
            ctx.close()
        b.close()
    print("WORKFLOW_ARCHITECTURE_BROWSER_PASS",flush=True)
finally:
    server.terminate();server.wait(timeout=5)
