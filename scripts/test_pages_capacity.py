"""Public capacity slice: actual qualified public shards, no source downloads."""
import json, os, re, subprocess, time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8093/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"pages-capacity-evidence"
OUT.mkdir(exist_ok=True)
manifest=json.loads((ROOT/"web/public-directory/manifest.json").read_text())
def capacity(r):
    s=str(r.get("capacity") or "").strip()
    if not re.fullmatch(r"[0-9]+",s):return None
    n=int(s)
    return n if n<=9007199254740991 else None
def stats(rows):
    known=[capacity(r) for r in rows if capacity(r) is not None]
    return {"records":len(rows),"reported":len(known),"unknown":len(rows)-len(known),"sum":sum(known) if known else None,"zero":known.count(0)}
sources={}
for key in ("nursing","dialysis"):
    shard=json.loads((ROOT/f"web/public-directory/{key}.json").read_text())
    assert shard["row_count"]==len(shard["records"])==manifest["sources"][key]["source_rows"]
    sources[key]=shard["records"]
    assert stats(sources[key])["reported"]>0
expected={key:stats(rows) for key,rows in sources.items()}
server=subprocess.Popen(["python","-m","http.server","8093","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for i in range(100):
        try:
            with urlopen(URL,timeout=2):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError("static test server unavailable")
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        measurements=[]
        for width in (390,768,1024,1440):
            page=b.new_page(viewport={"width":width,"height":900})
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            def metrics(expect):
                page.locator("#app .metrics .metric").first.wait_for()
                vals=page.locator("#app .metrics .metric strong").all_inner_texts()
                assert vals==[f'{expect["records"]:,}',f'{expect["sum"]:,}' if expect["sum"] is not None else "—",f'{expect["reported"]:,}',f'{expect["unknown"]:,}'],vals
                assert "records explicitly report zero" in page.locator("#app .metrics .metric").nth(2).inner_text()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
                assert not errors,errors
            page.goto(URL)
            page.get_by_role("link",name="Capacity explorer",exact=True).click()
            start=time.perf_counter()
            metrics(expected["nursing"])
            measurements.append({"width":width,"nursing_render_ms":round((time.perf_counter()-start)*1000,1)})
            page.get_by_role("columnheader",name="Certified beds",exact=True).wait_for()
            assert page.locator(".table-wrap").count()==2
            regional=page.locator(".table-wrap").nth(1)
            assert regional.locator("tbody tr").count()==56
            assert sum(int(s.replace(",","")) for s in regional.locator("tbody tr td:nth-child(2)").all_inner_texts())==expected["nursing"]["records"]
            assert sum(int(s.replace(",","")) for s in regional.locator("tbody tr td:last-child").all_inner_texts() if s!="—")==expected["nursing"]["sum"]
            page.screenshot(path=str(OUT/f"{width}-nursing-capacity.png"),full_page=True)
            regional.get_by_role("link",name="NY",exact=True).click()
            metrics(stats([r for r in sources["nursing"] if r["state"]=="NY"]))
            page.go_back()
            metrics(expected["nursing"])
            page.locator("select[name=source]").select_option("dialysis")
            page.locator("select[name=state]").select_option("NY")
            page.locator("select[name=reported]").select_option("known")
            page.locator("input[name=min]").fill("10")
            page.locator("select[name=sort]").select_option("capacity_desc")
            page.get_by_role("button",name="Apply filters").click()
            selected=[r for r in sources["dialysis"] if r["state"]=="NY" and capacity(r) is not None and capacity(r)>=10]
            metrics(stats(selected))
            page.get_by_role("columnheader",name="Dialysis stations",exact=True).wait_for()
            caps=[int(s.replace(",","")) for s in page.locator("tbody tr td:nth-child(3)").all_inner_texts()]
            assert caps==sorted(caps,reverse=True)
            assert all(n>=10 for n in caps)
            assert len(caps)==min(25,len(selected))
            page.screenshot(path=str(OUT/f"{width}-dialysis-filter.png"),full_page=True)
            if selected:
                page.locator("tbody tr").first.locator("a").first.click()
                page.get_by_role("link",name="Explore reported capacity in this jurisdiction").wait_for()
                page.get_by_role("link",name="Explore reported capacity in this jurisdiction").click()
                metrics(stats([r for r in sources["dialysis"] if r["state"]=="NY"]))
            page.goto(URL+"#capacity?source=nursing&reported=unknown")
            metrics(stats([r for r in sources["nursing"] if capacity(r) is None]))
            page.goto(URL+"#capacity?source=dialysis&state=NY&min=1000000")
            metrics(stats([r for r in sources["dialysis"] if r["state"]=="NY" and capacity(r) is not None and capacity(r)>=1000000]))
            page.get_by_text("No source records match these filters.",exact=False).wait_for()
            page.close()
        (OUT/"report.json").write_text(json.dumps({"actual_public_snapshot":True,"summaries":expected,"checks":measurements},indent=2))
        print("CAPACITY_BROWSER_PASS",json.dumps({"summaries":expected,"checks":measurements}),flush=True)
        b.close()
finally:
    server.terminate()
    server.wait(timeout=5)
