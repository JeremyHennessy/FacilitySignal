"""Pages slice 2: use only existing qualified public projections. No upstream downloads."""
import json, os, subprocess, time
from pathlib import Path
from playwright.sync_api import sync_playwright
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8091/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"pages-research-evidence"
OUT.mkdir(exist_ok=True)
meta=json.loads((ROOT/"web/public-directory/manifest.json").read_text())
# Assert the filter and geographic aggregation use the complete qualified jurisdiction set.
import re
js=(ROOT/"web/pages.js").read_text()
ui_states=re.search(r'const states="([^"]+)"',js).group(1).split()
assert len(ui_states)==len(set(ui_states))==56 and set(ui_states)==set(meta["jurisdictions"]), "UI jurisdiction set differs from the qualified snapshot"
hospital=json.loads((ROOT/"web/public-directory/hospital.json").read_text())["records"][0]
nursing=json.loads((ROOT/"web/public-directory/nursing.json").read_text())["records"][0]
all_provider_files=[s for s in meta["sources"] if not s.startswith("nursing-")]
expected_exact=sum(sum(r["ccn"]==hospital["ccn"] for r in json.loads((ROOT/f"web/public-directory/{s}.json").read_text())["records"]) for s in all_provider_files)
expected_citations={}
for source in ("nursing-health","nursing-fire"):
    recs=json.loads((ROOT/f"web/public-directory/{source}.json").read_text())["records"]
    group=[r for r in recs if r["ccn"]==nursing["ccn"] and r["state"]==nursing["state"]]
    expected_citations[source]=sum(r["citation_rows"] for r in group) if group else None
server=subprocess.Popen(["python","-m","http.server","8091","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for i in range(100):
        try:
            with urlopen(URL,timeout=2):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError("static test server unavailable")
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        report=[]
        for width in (390,768,1024,1440):
            page=b.new_page(viewport={"width":width,"height":900})
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            def shot(name):
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1"),(width,name)
                assert not errors,errors
                page.screenshot(path=str(OUT/f"{width}-{name}.png"),full_page=True,animations="disabled")
            page.goto(URL)
            page.get_by_text("48,004",exact=True).wait_for()
            shot("overview")
            start=time.perf_counter()
            page.locator("#global-q").fill(hospital["ccn"])
            page.locator("#global-search button").click()
            page.get_by_text(f"{expected_exact:,} matching source records across 7 of 7 provider sources.",exact=True).wait_for()
            report.append({"width":width,"all_source_exact_search_ms":round((time.perf_counter()-start)*1000,1)})
            assert page.locator(".table-wrap").count()>0
            shot("search")
            page.get_by_role("link",name="Market explorer",exact=True).click()
            page.get_by_text("48,004 provider source records across 7 of 7 sources.",exact=False).wait_for()
            assert page.locator("tbody tr").count()==56
            assert set(page.locator("tbody tr td:first-child").all_inner_texts())==set(meta["jurisdictions"])
            assert sum(int(v.replace(",","")) for v in page.locator("tbody tr td:last-child").all_inner_texts())==meta["provider_rows"]
            shot("geography")
            page.goto(URL+"#facilities?source=hospital&state=NY&sort=name_desc")
            page.locator("tbody tr").first.wait_for()
            assert 0<page.locator("tbody tr").count()<=25
            assert page.locator("select[name=sort]").input_value()=="name_desc"
            assert all("NY" in x.locator("td").nth(1).inner_text() for x in page.locator("tbody tr").all())
            shot("facilities")
            page.goto(URL+"#detail?source=nursing&id="+nursing["ccn"]+"&state="+nursing["state"])
            page.get_by_role("columnheader",name="Historical citation rows").wait_for()
            for label,key in [("Nursing health citations","nursing-health"),("Nursing fire citations","nursing-fire")]:
                row=page.get_by_role("row").filter(has_text=label)
                n=expected_citations[key]
                assert row.locator("td").nth(1).inner_text()==(f"{n:,}" if n is not None else "No matching group")
            shot("facility-evidence")
            page.goto(URL+"#search?field=id&q=ZZZZZZ")
            page.get_by_text("No matching published Care Compare source records.",exact=False).wait_for()
            page.close()
        (OUT/"report.json").write_text(json.dumps({"actual_public_snapshot":True,"source_rows":meta["provider_rows"],"checks":report},indent=2))
        print("PAGES_RESEARCH_BROWSER_PASS",json.dumps(report),flush=True)
        b.close()
finally:
    server.terminate()
    server.wait(timeout=5)
