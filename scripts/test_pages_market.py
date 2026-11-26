"""Browser tests for official geographic display and exact public regional counts."""
import json,os,subprocess,time
from collections import Counter
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8097/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"market-map-evidence"
OUT.mkdir(exist_ok=True)
manifest=json.loads((ROOT/"web/public-directory/manifest.json").read_text())
states=set(manifest["jurisdictions"])
source_counts={}
for key in manifest["sources"]:
    if key.startswith("nursing-"):continue
    d=json.loads((ROOT/f"web/public-directory/{key}.json").read_text())
    source_counts[key]=Counter(r["state"] for r in d["records"])
    assert sum(source_counts[key].values())==manifest["sources"][key]["source_rows"]
total=Counter()
for counts in source_counts.values():total.update(counts)
assert sum(total.values())==manifest["provider_rows"]
geometry=json.loads((ROOT/"web/market-boundaries.json").read_text())
assert {r["state"] for r in geometry["regions"]}==states
server=subprocess.Popen(["python","-m","http.server","8097","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            with urlopen(URL,timeout=2):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError("local HTTP unavailable")
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        checks=[]
        for width in (390,768,1024,1440):
            page=b.new_page(viewport={"width":width,"height":900})
            errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
            start=time.perf_counter()
            page.goto(URL+"#geography")
            page.locator(".market-region").first.wait_for()
            assert page.locator(".market-region").count()==56
            observed={x.get_attribute("data-state"):int(x.get_attribute("data-count")) for x in page.locator(".market-region").all()}
            assert observed=={st:total[st] for st in states}
            assert page.locator("tbody tr").count()==56
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            assert not errors,errors
            page.screenshot(path=str(OUT/f"{width}-national-market.png"),full_page=False)
            elapsed=round((time.perf_counter()-start)*1000,1)
            page.locator("select[name=source]").select_option("hospital")
            page.locator("select[name=state]").select_option("NY")
            page.get_by_role("button",name="Apply map filters").click()
            page.get_by_role("heading",name="NY market").wait_for()
            page.locator(".market-region[data-state=NY][aria-current=true]").wait_for()
            observed={x.get_attribute("data-state"):int(x.get_attribute("data-count")) for x in page.locator(".market-region").all()}
            assert observed=={st:source_counts["hospital"][st] for st in states}
            assert page.locator(".market-selected-count").inner_text()==f"Hospitals · {source_counts['hospital']['NY']:,} source records"
            # Keyboard activation of a geographic region (small polygons also selectable in form).
            page.locator(".market-region[data-state=VT]").focus()
            page.keyboard.press("Enter")
            page.get_by_role("heading",name="VT market").wait_for()
            page.locator(".market-region[data-state=VT][aria-current=true]").wait_for()
            page.get_by_role("link",name="Open selected category in directory").click()
            page.locator("tbody tr").first.wait_for()
            assert "state=VT" in page.url and "source=hospital" in page.url
            page.go_back()
            page.get_by_role("heading",name="VT market").wait_for()
            page.locator(".market-region[data-state=VT][aria-current=true]").wait_for()
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            # Geometry failure leaves original research table and selection available.
            page.route("**/web/market-boundaries.json",lambda route:route.fulfill(status=503,body="unavailable"))
            page.goto(URL+"#geography?source=all&state=NY")
            page.get_by_text("Map geometry unavailable.",exact=False).wait_for()
            assert page.locator("tbody tr").count()==56
            assert page.get_by_role("heading",name="NY market").count()==1
            assert page.locator(".market-region").count()==0
            page.close()
            checks.append({"width":width,"regions":56,"national_render_ms_including_screenshot":elapsed,"source_counts":True,"keyboard_drilldown":True,"failure_fallback":True})
        b.close()
    (OUT/"report.json").write_text(json.dumps({"actual_public_projections":True,"boundary_sha256":geometry["source_sha256"],"checks":checks},indent=2))
    print("MARKET_MAP_BROWSER_PASS",json.dumps(checks),flush=True)
finally:
    server.terminate();server.wait(timeout=5)
