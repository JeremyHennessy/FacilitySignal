"""Public visual release gate: normal URL, browser-loaded assets, screenshots.

Local candidate mode uses the identical route checks. The live mode deliberately
does not append a cache-busting revision to the page or asset requests. Review
the uploaded screenshots before reporting any public release complete.
"""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from urllib.request import urlopen
from collections import Counter
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
PUBLIC_URL="https://jeremyhennessy.github.io/FacilitySignal/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"pages-live-visual-evidence"
OUT.mkdir(exist_ok=True)
def sha(data):return hashlib.sha256(data).hexdigest()
ASSETS=("web/pages.js","web/pages.css")
HASHES={x:sha((ROOT/x).read_bytes()) for x in ("index.html",*ASSETS,"web/market-boundaries.json","web/market-summary.json")}
VERSIONS={x:x+"?v="+HASHES[x][:16] for x in ASSETS}
MANIFEST=json.loads((ROOT/"web/public-directory/manifest.json").read_text())
TOTAL=MANIFEST["provider_rows"]
HOSPITAL=Counter(r["state"] for r in json.loads((ROOT/"web/public-directory/hospital.json").read_text())["records"])
PROVIDER=json.loads((ROOT/"web/public-directory/nursing.json").read_text())["records"][0]
ROUTES=[
    ("overview","overview",lambda page:page.get_by_text(f"{TOTAL:,}",exact=True)),
    ("search","search",lambda page:page.get_by_role("heading",name="Unified search",exact=True)),
    ("advanced","advanced?source=nursing&state=NY&min=100&max=199&run=1",lambda page:page.locator('.advanced-status[data-complete="true"]')),
    ("industry","industry?state=NY",lambda page:page.get_by_role("heading",name="Water treatment & dialysis")),
    ("procurement","procurement",lambda page:page.locator('.procurement-pilot[data-qualified="true"]')),
    ("market","geography?source=hospital&state=NY",lambda page:page.locator(".market-region[data-state=NY][aria-current=true]")),
    ("directory","facilities?source=hospital&state=NY",lambda page:page.locator("tbody tr").first),
    ("profile","detail?"+urlencode({"source":"nursing","id":PROVIDER["ccn"],"state":PROVIDER["state"],"section":"sources"}),lambda page:page.get_by_role("heading",name="Evidence availability for this record")),
    ("certifications","certifications",lambda page:page.get_by_role("heading",name="Certifications & laboratories",exact=True)),
    ("capacity","capacity?source=dialysis&state=NY",lambda page:page.locator(".capacity-band").first),
    ("services","services",lambda page:page.get_by_role("heading",name="Hospital service provision codes")),
    ("compliance","compliance-research",lambda page:page.get_by_role("heading",name="Literal correction wording")),
    ("citations","citations?source=nursing-health&state=NY",lambda page:page.get_by_role("columnheader",name="Historical citation rows")),
    ("hospital-surveys","hospital-surveys",lambda page:page.get_by_role("heading",name="Hospital survey coverage",exact=True)),
    ("equipment","equipment-environment",lambda page:page.get_by_role("heading",name="FDA mammography directory")),
    ("ownership","ownership",lambda page:page.get_by_role("heading",name="Ownership evidence coverage",exact=True)),
    ("sources","sources",lambda page:page.locator("tbody tr").first),
    ("data","data-evidence",lambda page:page.get_by_role("heading",name="Snapshot retention checkpoint")),
]
def ordinary_entry(browser,base,utm,attempts):
    """New context for each propagation retry; normal navigation, no revision query."""
    last="no navigation"
    for i in range(attempts):
        context=browser.new_context(viewport={"width":1440,"height":900})
        page=context.new_page()
        responses=[]
        page.on("response",lambda resp:responses.append(resp))
        try:
            res=page.goto(base+utm+"#geography",wait_until="load",timeout=30000)
            assert res and res.status==200,"HTTP status"
            assert sha(res.body())==HASHES["index.html"],"Ordinary entry point is stale"
            page.locator(".market-region").first.wait_for(timeout=8000)
            assert page.locator(".market-region").count()==len(MANIFEST["jurisdictions"])
            assert page.locator("script[src]").get_attribute("src")==VERSIONS["web/pages.js"]
            assert page.locator("link[rel=stylesheet]").get_attribute("href")==VERSIONS["web/pages.css"]
            for asset,version in VERSIONS.items():
                seen=[resp for resp in responses if resp.url==base+version]
                assert seen and sha(seen[-1].body())==HASHES[asset],"Browser received stale "+asset
            geo=[resp for resp in responses if resp.url==base+"web/market-boundaries.json"]
            assert geo and sha(geo[-1].body())==HASHES["web/market-boundaries.json"],"Browser received stale geography"
            summary=[resp for resp in responses if resp.url==base+"web/market-summary.json?v="+MANIFEST["source_database_sha256"][:16]]
            assert summary and sha(summary[-1].body())==HASHES["web/market-summary.json"],"Browser received stale regional summary"
            assert page.locator('[data-aggregation="precomputed"]').count()==1
            # Warm-cache reload is deliberately in the same context and ordinary URL.
            page.reload(wait_until="load")
            page.locator(".market-region").first.wait_for(timeout=15000)
            assert page.locator(".market-region").count()==len(MANIFEST["jurisdictions"])
            assert page.locator("script[src]").get_attribute("src")==VERSIONS["web/pages.js"]
            page.locator(".market-map-frame").screenshot(path=str(OUT/("ordinary-utm-map.png" if utm else "ordinary-map.png")))
            return {"url":base+utm+"#geography","fresh_and_warm_map":True,"attempts":i+1,"actual_loaded_assets":HASHES}
        except Exception as e:
            last=str(e)[:500]
            if i+1==attempts:raise AssertionError("Normal user URL failed: "+last) from e
            time.sleep(5)
        finally:context.close()
def run(base,local):
    results=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        entries=[ordinary_entry(browser,base,q,1 if local else 36) for q in ("","?utm_source=chatgpt.com")]
        for width in (390,768,1024,1440):
            ctx=browser.new_context(viewport={"width":width,"height":900})
            page=ctx.new_page()
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            for name,route,ready in ROUTES:
                page.goto(base+"#"+route,wait_until="load",timeout=30000)
                ready(page).wait_for(timeout=30000)
                assert not errors,(name,errors)
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1"),(width,name)
                page.evaluate("window.scrollTo(0,0)")
                page.screenshot(path=str(OUT/f"{width}-{name}.png"),animations="disabled")
                if name=="procurement":
                    assert page.locator(".procurement-pilot .metric strong").all_inner_texts()==["100","100"]
                    page.locator(".procurement-pilot").screenshot(path=str(OUT/f"{width}-procurement-pilot.png"))
                if name=="advanced":
                    page.locator(".advanced-form").screenshot(path=str(OUT/f"{width}-advanced-filters.png"))
                    page.locator(".advanced-results").screenshot(path=str(OUT/f"{width}-advanced-results.png"))
                if name=="market":
                    assert page.locator(".market-region").count()==56
                    actual={x.get_attribute("data-state"):int(x.get_attribute("data-count")) for x in page.locator(".market-region").all()}
                    assert actual=={s:HOSPITAL[s] for s in MANIFEST["jurisdictions"]}
                    page.locator(".market-map-frame").screenshot(path=str(OUT/f"{width}-market-map.png"))
                    page.locator(".market-selection").screenshot(path=str(OUT/f"{width}-market-selection.png"))
                results.append({"width":width,"route":name,"screenshot":f"{width}-{name}.png"})
            ctx.close()
        browser.close()
    report={"scope":"local candidate" if local else "ordinary public URL","revision":os.environ.get("GITHUB_SHA","local"),"entry_checks":entries,"screens":results,"visual_review_required":True}
    (OUT/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("PAGES_VISUAL_CAPTURE_PASS",json.dumps({"scope":report["scope"],"screens":len(results),"entry_checks":entries}),flush=True)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--local",action="store_true")
    a=p.parse_args()
    if not a.local:run(PUBLIC_URL,False);return
    server=subprocess.Popen(["python","-m","http.server","8098","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    base="http://127.0.0.1:8098/"
    try:
        for i in range(100):
            try:
                with urlopen(base,timeout=2):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError("local HTTP unavailable")
        run(base,True)
    finally:server.terminate();server.wait(timeout=5)
if __name__=="__main__":main()
