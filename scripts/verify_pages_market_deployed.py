"""Verify exact deployed market UI and official display geometry after promotion."""
import hashlib,json,os,time
from collections import Counter
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL="https://jeremyhennessy.github.io/FacilitySignal/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"market-live-evidence"
OUT.mkdir(exist_ok=True)
paths=["index.html","web/pages.js","web/pages.css","web/market-boundaries.json"]
hashes={x:hashlib.sha256((ROOT/x).read_bytes()).hexdigest() for x in paths}
manifest=json.loads((ROOT/"web/public-directory/manifest.json").read_text())
counts=Counter(r["state"] for r in json.loads((ROOT/"web/public-directory/hospital.json").read_text())["records"])
rev=os.environ.get("GITHUB_SHA","local")
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,args=["--no-sandbox"])
    req=p.request.new_context()
    for i in range(36):
        seen={}
        for x in paths:
            response=req.get(URL+("" if x=="index.html" else x)+"?rev="+rev,timeout=20000)
            if response.ok:seen[x]=hashlib.sha256(response.body()).hexdigest()
        if seen==hashes:break
        if i==35:raise AssertionError("Exact deployed asset hash mismatch "+json.dumps(seen))
        time.sleep(5)
    req.dispose()
    for width in (390,1440):
        page=b.new_page(viewport={"width":width,"height":900})
        errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(URL+"?rev="+rev+"#geography?source=hospital&state=NY")
        page.locator(".market-region[data-state=NY][aria-current=true]").wait_for()
        assert page.locator(".market-region").count()==56
        seen={x.get_attribute("data-state"):int(x.get_attribute("data-count")) for x in page.locator(".market-region").all()}
        assert seen=={s:counts[s] for s in manifest["jurisdictions"]}
        assert page.locator(".market-selected-count").inner_text()==f"Hospitals · {counts['NY']:,} source records"
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
        assert not errors,errors
        page.get_by_role("link",name="Open selected category in directory").click()
        page.locator("tbody tr").first.wait_for()
        assert "source=hospital" in page.url and "state=NY" in page.url
        page.close()
    b.close()
report={"url":URL,"revision":rev,"asset_sha256":hashes,"widths":[390,1440],"checks":["exact deployed assets and boundaries","56 map regions","hospital source count reconciliation","selected jurisdiction","directory drilldown","no browser errors"]}
(OUT/"report.json").write_text(json.dumps(report,indent=2)+"\n")
print("LIVE_MARKET_RELEASE_PASS",json.dumps(report),flush=True)
