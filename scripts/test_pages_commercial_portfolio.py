"""Exercise expanded aggregate and local portfolio research using the actual browser routes."""
import json, os, subprocess, time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8100/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"commercial-portfolio-evidence"
OUT.mkdir(exist_ok=True)
D=json.loads((ROOT/"web/public-directory/nursing.json").read_text())["records"][0]
G={s["id"]:s["groups"] for s in json.loads((ROOT/"web/public-intelligence.json").read_text())["sections"]}
server=subprocess.Popen(["python","-m","http.server","8100","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
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
            for route in ("financial-research","equipment-environment"):
                page.goto(URL+"#"+route);page.locator("#app .intelligence-table").last.wait_for()
                tables=page.locator("#app .intelligence-table");assert tables.count()==len(G[route])
                for i,g in enumerate(G[route]):
                    assert [r.locator("td").all_inner_texts() for r in tables.nth(i).locator("tbody tr").all()]==[["—" if x is None else f"{x:,}" if type(x) is int else x for x in row] for row in g["rows"]]
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                page.screenshot(path=str(OUT/f"{width}-{route}.png"),full_page=True)
                if route=="financial-research":
                    inputs=page.get_by_label("Filter measure names")
                    assert inputs.count()==2
                    inputs.first.fill("equipment")
                    expected=sum("equipment" in r[0].lower() for r in G[route][1]["rows"])
                    assert tables.nth(1).locator("tbody tr:visible").count()==expected
            page.goto(URL+"#procurement");page.locator(".procurement-pilot[data-qualified=true]").wait_for()
            assert page.get_by_role("heading",name="Sampled award field coverage").count()==1
            page.screenshot(path=str(OUT/f"{width}-procurement.png"),full_page=True)
            page.goto(URL+"#detail?"+urlencode({"source":"nursing","id":D["ccn"],"state":D["state"]}))
            save=page.get_by_role("button",name="Save to research portfolio");save.click()
            assert page.get_by_role("button",name="Saved to research portfolio").is_disabled()
            page.get_by_role("link",name="Open saved portfolio").click()
            page.locator(".portfolio-count").wait_for()
            assert "1 saved source records" in page.locator(".portfolio-count").inner_text()
            page.reload();page.locator(".portfolio-count").wait_for()
            assert "1 saved source records" in page.locator(".portfolio-count").inner_text()
            assert page.get_by_role("link",name=D["name"],exact=True).count()==1
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.screenshot(path=str(OUT/f"{width}-portfolio.png"),full_page=True)
            page.locator("select[name=source]").select_option("hospital")
            page.get_by_role("button",name="Filter",exact=True).click()
            page.get_by_text("No saved records match these filters.").wait_for()
            page.goto(URL+"#saved-portfolio");page.get_by_role("button",name="Remove",exact=True).click()
            assert "0 saved source records" in page.locator(".portfolio-count").inner_text()
            page.evaluate("localStorage.setItem('facilitysignal.public.portfolio.v1','{broken')")
            page.reload();page.get_by_text("Saved portfolio unavailable:",exact=False).wait_for()
            assert page.evaluate("localStorage.getItem('facilitysignal.public.portfolio.v1')")=="{broken"
            assert not errors,errors
            ctx.close()
        b.close()
    print("COMMERCIAL_PORTFOLIO_BROWSER_PASS",flush=True)
finally:
    server.terminate();server.wait(timeout=5)
