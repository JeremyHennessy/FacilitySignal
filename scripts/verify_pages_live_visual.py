"""Public visual release gate: normal URL, browser-loaded assets, screenshots.

Local candidate mode uses the identical route checks. The live mode deliberately
does not append a cache-busting revision to the page or asset requests. Review
the uploaded screenshots before reporting any public release complete.
"""
import argparse,csv,hashlib,json,os,subprocess,time
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
HASHES={x:sha((ROOT/x).read_bytes()) for x in ("index.html",*ASSETS,"web/market-boundaries.json","web/market-summary.json","web/public-directory/manifest.json","web/public-directory/long-term-hospital.json","web/public-intelligence.json","web/dialysis-service-evidence.json","web/public-directory/dialysis.json","web/hha-service-evidence.json","web/public-directory/home-health.json","web/nursing-chain-evidence.json")}
VERSIONS={x:x+"?v="+HASHES[x][:16] for x in ASSETS}
MANIFEST=json.loads((ROOT/"web/public-directory/manifest.json").read_text())
TOTAL=MANIFEST["provider_rows"]
LTCH_META=MANIFEST["field_enrichments"]["long-term-hospital"]
LTCH=next(r for r in json.loads((ROOT/"web/public-directory/long-term-hospital.json").read_text())["records"] if r["capacity"])
HOSPITAL=Counter(r["state"] for r in json.loads((ROOT/"web/public-directory/hospital.json").read_text())["records"])
PROVIDER=json.loads((ROOT/"web/public-directory/nursing.json").read_text())["records"][0]
DIALYSIS_OBS=json.loads((ROOT/"web/dialysis-service-evidence.json").read_text())["records"]
DIALYSIS_ROWS=json.loads((ROOT/"web/public-directory/dialysis.json").read_text())["records"]
DIALYSIS_LINKED=next(r for r in DIALYSIS_ROWS if r["ccn"] in DIALYSIS_OBS)
DIALYSIS_UNLINKED=next(r for r in DIALYSIS_ROWS if r["ccn"] not in DIALYSIS_OBS)
HHA_OBS=json.loads((ROOT/"web/hha-service-evidence.json").read_text())["records"]
HHA_ROWS=json.loads((ROOT/"web/public-directory/home-health.json").read_text())["records"]
HHA_PROFILE=next(r for r in HHA_ROWS if HHA_OBS[r["state"]+":"+r["ccn"]]["Nursing Care"]=="dash_marker")
ROUTES=[
    ("overview","overview",lambda page:page.get_by_text(f"{TOTAL:,}",exact=True)),
    ("search","search",lambda page:page.get_by_role("heading",name="Unified search",exact=True)),
    ("advanced","advanced?source=nursing&state=NY&min=100&max=199&run=1",lambda page:page.locator('.advanced-status[data-complete="true"]')),
    ("industry","industry?state=NY",lambda page:page.get_by_role("heading",name="Water treatment & dialysis")),
    ("procurement","procurement",lambda page:page.locator('.procurement-pilot[data-qualified="true"]')),
    ("market","geography?source=hospital&state=NY",lambda page:page.locator(".market-region[data-state=NY][aria-current=true]")),
    ("directory","facilities?source=hospital&state=NY",lambda page:page.locator("tbody tr").first),
    ("profile","detail?"+urlencode({"source":"nursing","id":PROVIDER["ccn"],"state":PROVIDER["state"],"section":"sources"}),lambda page:page.get_by_role("heading",name="Evidence availability for this record")),
    ("profile-summary","detail?"+urlencode({"source":"nursing","id":PROVIDER["ccn"],"state":PROVIDER["state"]}),lambda page:page.get_by_role("heading",name="Continue this research")),
    ("certifications","certifications",lambda page:page.get_by_role("heading",name="Certifications & laboratories",exact=True)),
    ("capacity","capacity?source=dialysis&state=NY",lambda page:page.locator(".capacity-band").first),
    ("ltch-capacity","capacity?source=long-term-hospital",lambda page:page.locator(".ltch-capacity-table")),
    ("ltch-profile","detail?"+urlencode({"source":"long-term-hospital","id":LTCH["ccn"],"state":LTCH["state"],"section":"services"}),lambda page:page.get_by_role("heading",name="Reported capacity and service evidence")),
    ("services","services",lambda page:page.get_by_role("heading",name="ASC service provision arrangements")),
    ("dialysis-services","dialysis-services?field=hmdlys_srvc_sw&evidence=reported_yes",lambda page:page.locator(".dialysis-status[data-ready=true]")),
    ("hha-services","hha-services?field=Nursing+Care&evidence=yes",lambda page:page.locator(".hha-status[data-ready=true]")),
    ("hha-profile","detail?"+urlencode({"source":"home-health","id":HHA_PROFILE["ccn"],"state":HHA_PROFILE["state"],"section":"services"}),lambda page:page.locator(".hha-profile[data-evidence=qualified]")),
    ("dialysis-linked","detail?"+urlencode({"source":"dialysis","id":DIALYSIS_LINKED["ccn"],"state":DIALYSIS_LINKED["state"],"section":"services"}),lambda page:page.locator(".dialysis-profile[data-evidence=corroborated]")),
    ("dialysis-unlinked","detail?"+urlencode({"source":"dialysis","id":DIALYSIS_UNLINKED["ccn"],"state":DIALYSIS_UNLINKED["state"],"section":"services"}),lambda page:page.locator(".dialysis-profile[data-evidence=unlinked]")),
    ("financial-research","financial-research",lambda page:page.get_by_role("heading",name="Home health FY2024 cost-report structure")),
    ("saved-portfolio","saved-portfolio",lambda page:page.locator(".portfolio-count")),
    ("hospital-infrastructure","hospital-infrastructure",lambda page:page.get_by_role("heading",name="Hospital infrastructure and affiliation count coverage")),
    ("nursing-portfolios","nursing-portfolios",lambda page:page.get_by_role("heading",name="Nursing cross-source group corroboration")),
    ("compliance","compliance-research",lambda page:page.get_by_role("heading",name="Nursing inspection and dispute flags")),
    ("citations","citations?source=nursing-health&state=NY",lambda page:page.get_by_role("columnheader",name="Historical citation rows")),
    ("hospital-surveys","hospital-surveys",lambda page:page.get_by_role("heading",name="Hospital survey coverage",exact=True)),
    ("equipment","equipment-environment",lambda page:page.get_by_role("heading",name="FDA mammography directory")),
    ("ownership","ownership",lambda page:page.get_by_role("heading",name="Ownership evidence coverage",exact=True)),
    ("sources","sources",lambda page:page.locator("tbody tr").first),
    ("data","data-evidence",lambda page:page.get_by_role("heading",name="Hospital-to-laboratory reference evidence")),
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
            summary=[resp for resp in responses if resp.url==base+"web/market-summary.json?v="+LTCH_META["projection_sha256"][:16]]
            assert summary and sha(summary[-1].body())==HASHES["web/market-summary.json"],"Browser received stale regional summary"
            assert page.locator('[data-aggregation="precomputed"]').count()==1
            manifests=[resp for resp in responses if resp.url==base+"web/public-directory/manifest.json"]
            assert manifests and sha(manifests[-1].body())==HASHES["web/public-directory/manifest.json"],"Browser received stale public manifest"
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
            responses=[];page.on("response",lambda resp:responses.append(resp))
            for name,route,ready in ROUTES:
                responses.clear()
                page.goto(base+"#"+route,wait_until="load",timeout=30000)
                ready(page).wait_for(timeout=30000)
                assert not errors,(name,errors)
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1"),(width,name)
                page.evaluate("window.scrollTo(0,0)")
                page.screenshot(path=str(OUT/f"{width}-{name}.png"),animations="disabled")
                if name=="overview":
                    assert page.locator(".home-discovery-form").count()==1
                    assert page.locator(".home-workflow").count()==4
                    assert page.locator("nav[aria-label='Primary navigation'] a").count()==23
                    assert page.locator(".home-coverage").evaluate("(e)=>!e.open")
                    page.locator(".home-discovery-form select[name=source]").select_option("hospital")
                    page.locator(".home-discovery-form select[name=state]").select_option("NY")
                    page.get_by_role("button",name="Find matching facilities").click()
                    page.locator('.advanced-status[data-complete="true"]').wait_for()
                    assert page.locator("select[name=source]").input_value()=="hospital"
                    assert page.locator("select[name=state]").input_value()=="NY"
                    page.go_back();page.locator(".home-discovery-form").wait_for()
                    page.locator(".home-coverage summary").click()
                    assert page.locator(".home-coverage").evaluate("(e)=>e.open")
                    page.locator(".home-coverage summary").click()
                    page.locator(".home-workflows").screenshot(path=str(OUT/f"{width}-home-workflows.png"))
                if name=="financial-research":
                    assert page.locator("#app .intelligence-table").count()==5
                    seen=[r for r in responses if r.url==base+"web/public-intelligence.json"]
                    assert seen and sha(seen[-1].body())==HASHES["web/public-intelligence.json"]
                    page.locator("#app").screenshot(path=str(OUT/f"{width}-finance-full.png"))
                if name=="equipment":
                    page.get_by_role("heading",name="Hospital laboratory reference corroboration").wait_for()
                    assert page.locator("#app .intelligence-table").count()==6
                    page.locator("#app").screenshot(path=str(OUT/f"{width}-environment-full.png"))
                if name=="saved-portfolio":
                    assert "0 saved source records" in page.locator(".portfolio-count").inner_text()
                if name=="hospital-infrastructure":
                    assert page.locator("#app .intelligence-table").count()==4
                    seen=[r for r in responses if r.url==base+"web/public-intelligence.json"]
                    assert seen and sha(seen[-1].body())==HASHES["web/public-intelligence.json"],"Stale hospital aggregate evidence"
                    page.locator("#app").screenshot(path=str(OUT/f"{width}-hospital-infrastructure-full.png"))
                if name=="nursing-portfolios":
                    assert page.locator("#app .intelligence-table").count()==3
                    assert "Publisher-defined affiliations are not legal ownership" in page.locator("#app").inner_text()
                    loc=page.locator(".chain-explorer[data-ready=true]");loc.wait_for()
                    assert loc.locator(".chain-status").get_attribute("data-total")=="612"
                    got=[r for r in responses if r.url==base+"web/nursing-chain-evidence.json?v="+HASHES["web/nursing-chain-evidence.json"][:16]]
                    assert got and sha(got[-1].body())==HASHES["web/nursing-chain-evidence.json"],"Stale chain pack"
                    loc.screenshot(path=str(OUT/f"{width}-chain-directory.png"))
                    loc.locator(".chain-groups tbody tr a").first.click()
                    detail=page.locator(".chain-explorer[data-ready=true]");detail.locator(".chain-members").wait_for()
                    assert int(detail.locator(".chain-status").get_attribute("data-total"))>0
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                    detail.screenshot(path=str(OUT/f"{width}-chain-members.png"))
                    detail.locator(".chain-members tbody tr a").first.click()
                    page.locator(".nursing-chain-profile[data-evidence=assigned]").wait_for()
                    page.locator(".nursing-chain-profile").screenshot(path=str(OUT/f"{width}-chain-profile.png"))
                    page.get_by_role("link",name="Back to results").click()
                    page.locator(".chain-explorer[data-ready=true] .chain-members").wait_for()
                    page.goto(base+"#nursing-portfolios")
                    page.locator(".chain-explorer[data-ready=true] .chain-groups").wait_for()
                    page.get_by_role("heading",name="Nursing cross-source group corroboration").wait_for()
                    seen=[r for r in responses if r.url==base+"web/public-intelligence.json"]
                    assert seen and sha(seen[-1].body())==HASHES["web/public-intelligence.json"],"Stale nursing aggregate evidence"
                    page.locator("#app").screenshot(path=str(OUT/f"{width}-nursing-portfolio-full.png"))
                if name=="hha-services":
                    assert page.locator(".hha-status").get_attribute("data-total")=="10208"
                    received=[r for r in responses if r.url==base+"web/hha-service-evidence.json?v="+HASHES["web/hha-service-evidence.json"][:16]]
                    assert received and sha(received[-1].body())==HASHES["web/hha-service-evidence.json"],"Stale home health evidence"
                    page.locator(".hha-service-form").screenshot(path=str(OUT/f"{width}-hha-filters.png"))
                    page.locator(".hha-results").screenshot(path=str(OUT/f"{width}-hha-results.png"))
                if name=="hha-profile":
                    assert page.locator('.hha-profile [data-field="Nursing Care"] dd').inner_text()=="Unknown (source dash)"
                    page.locator(".hha-profile").screenshot(path=str(OUT/f"{width}-hha-profile-evidence.png"))
                if name=="dialysis-services":
                    assert page.locator(".dialysis-status").get_attribute("data-total")=="2043"
                    received=[r for r in responses if r.url==base+"web/dialysis-service-evidence.json?v="+HASHES["web/dialysis-service-evidence.json"][:16]]
                    assert received and sha(received[-1].body())==HASHES["web/dialysis-service-evidence.json"],"Stale or unavailable service projection"
                    page.locator(".dialysis-service-form").screenshot(path=str(OUT/f"{width}-dialysis-filters.png"))
                    page.locator(".dialysis-results").screenshot(path=str(OUT/f"{width}-dialysis-results.png"))
                if name in ("dialysis-linked","dialysis-unlinked"):
                    page.locator(".dialysis-profile").screenshot(path=str(OUT/f"{width}-{name}-evidence.png"))
                if name=="ltch-capacity":
                    assert page.locator(".metrics .metric strong").all_inner_texts()==["311","21,765","305","6"]
                    seen=[r for r in responses if r.url==base+"web/public-directory/long-term-hospital.json?v="+LTCH_META["projection_sha256"][:16]]
                    assert seen and sha(seen[-1].body())==HASHES["web/public-directory/long-term-hospital.json"],"Browser loaded wrong LTCH projection"
                    page.locator(".metrics").screenshot(path=str(OUT/f"{width}-ltch-metrics.png"))
                    page.locator(".ltch-capacity-table").screenshot(path=str(OUT/f"{width}-ltch-results.png"))
                    if width<=768: assert page.locator(".ltch-capacity-table").evaluate("(e)=>{e.scrollLeft=100;const moved=e.scrollLeft>0;e.scrollLeft=0;return moved}")
                if name=="ltch-profile":
                    assert page.get_by_text("Total beds",exact=True).count()==1
                    assert page.get_by_text(f'{int(LTCH["capacity"]):,}',exact=True).count()>=1
                if name in ("services","data","compliance"):
                    seen=[r for r in responses if r.url==base+"web/public-intelligence.json"]
                    assert seen and sha(seen[-1].body())==HASHES["web/public-intelligence.json"],"Browser loaded wrong aggregate evidence"
                    groups=("ASC service provision arrangements","Home health reported services","Hospital enrollment subgroup classifications","Hospital service provision — matched research subset","Hospital infrastructure and affiliation count coverage") if name=="services" else ("Nursing inspection and dispute flags",) if name=="compliance" else ("CLIA certificate code distribution","Hospital-to-laboratory reference evidence","National field audit coverage","Reported nursing-home chain membership","Nursing cross-source group corroboration","Reported PECOS organizational relationship classes","Organization classification agreement and conflicts","Reported ownership-change types","Hospital registry and directory comparison","CLIA historical termination-code scopes","CLIA certificates by reported status scope","CLIA reported facility-type classifications","CLIA accreditation declarations and confirmations","CLIA certificate date diagnostics","CLIA identifier and affiliation-reference diagnostics")
                    for n,g in enumerate(groups):page.locator(f'[aria-label^="{g}"]').screenshot(path=str(OUT/f"{width}-{name}-group-{n}.png"))
                if name=="profile-summary":
                    page.locator(".dossier-evidence[data-ready=true]").wait_for()
                    assert page.get_by_role("columnheader",name="Historical citation rows").count()==1
                    page.screenshot(path=str(OUT/f"{width}-integrated-nursing-dossier.png"),full_page=True)
                    page.get_by_role("link",name="Location & peers",exact=True).click()
                    location=page.locator(".profile-location[data-ready=true]");location.wait_for()
                    assert location.get_attribute("data-complete")=="true"
                    assert location.locator(".location-match-count").count()==1
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                    page.screenshot(path=str(OUT/f"{width}-profile-location.png"),full_page=True)
                    page.go_back();page.locator(".dossier-evidence[data-ready=true]").wait_for()
                    page.locator(".profile-research-actions").screenshot(path=str(OUT/f"{width}-profile-actions.png"))
                    assert page.get_by_role("link",name="All provider records in reported city").count()==1
                    page.get_by_role("button",name="Save to research portfolio").click()
                    page.get_by_role("link",name="Open saved portfolio").click()
                    page.locator(".portfolio-count").wait_for()
                    assert "1 saved source records" in page.locator(".portfolio-count").inner_text()
                    page.reload();page.locator(".portfolio-count").wait_for()
                    assert "1 saved source records" in page.locator(".portfolio-count").inner_text()
                    page.screenshot(path=str(OUT/f"{width}-saved-portfolio-populated.png"))
                    second=DIALYSIS_ROWS[0]
                    page.goto(base+"#detail?"+urlencode({"source":"dialysis","id":second["ccn"],"state":second["state"]}))
                    page.get_by_role("button",name="Save to research portfolio").click()
                    page.get_by_role("link",name="Open saved portfolio").click()
                    page.locator(".portfolio-count").wait_for()
                    assert "2 saved source records" in page.locator(".portfolio-count").inner_text()
                    with page.expect_download() as dl:
                        page.get_by_role("button",name="Export filtered portfolio CSV").click()
                    with dl.value.path().open(encoding="utf-8",newline="") as f:
                        saved=list(csv.DictReader(f))
                    assert len(saved)==2 and all(r["saved_source_release"] and r["source_identifier"] for r in saved)
                    wrap=page.locator(".portfolio-results")
                    assert wrap.evaluate("(e)=>Array.from(e.querySelectorAll('td button')).every(b=>getComputedStyle(b).whiteSpace==='nowrap'&&b.scrollWidth<=b.clientWidth+1)")
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                    if wrap.evaluate("(e)=>e.scrollWidth>e.clientWidth+1"):
                        assert page.locator(".portfolio-scroll-hint").is_visible()
                        assert wrap.evaluate("(e)=>{e.scrollLeft=e.scrollWidth;const t=e.querySelector('tbody tr td:last-child');return e.scrollLeft>0&&t.getBoundingClientRect().right<=e.getBoundingClientRect().right+2}")
                        page.screenshot(path=str(OUT/f"{width}-portfolio-export-scrolled.png"),full_page=True)
                        wrap.evaluate("(e)=>{e.scrollLeft=0}")
                    page.screenshot(path=str(OUT/f"{width}-portfolio-export.png"),full_page=True)
                    page.locator(".portfolio-provider-cell input").nth(0).check()
                    page.locator(".portfolio-provider-cell input").nth(1).check()
                    page.get_by_role("button",name="Compare selected (2 / 4)").click()
                    page.locator(".comparison-table").wait_for()
                    assert "2 exact published records resolved" in page.locator(".comparison-status").inner_text()
                    with page.expect_download() as dl:
                        page.get_by_role("button",name="Export comparison CSV").click()
                    with dl.value.path().open(encoding="utf-8",newline="") as f:
                        exported=list(csv.reader(f))
                    report={r[0]:r[1:] for r in exported[1:]}
                    assert len(exported[0])==3 and all(len(r)==3 for r in exported)
                    assert report["Source identifier"]==page.locator(".comparison-table tbody tr").filter(has_text="Source identifier").locator("td").all_inner_texts()[1:]
                    assert all("does not establish compliance" in v for v in report["Evidence limitations"])
                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                    page.screenshot(path=str(OUT/f"{width}-facility-comparison.png"),full_page=True)
                    if width<=720:
                        wrap=page.locator(".comparison-table")
                        assert page.locator(".comparison-scroll-hint").is_visible()
                        assert wrap.evaluate("(e)=>{e.scrollLeft=e.scrollWidth;const frame=e.getBoundingClientRect();return e.scrollLeft>0&&Array.from(e.querySelectorAll(\"tr\")).every(tr=>{const cells=tr.cells,first=cells[0].getBoundingClientRect(),last=cells[cells.length-1].getBoundingClientRect();return last.left>=first.right-2&&last.right<=frame.right+2&&last.width>=100})}"),"Final provider column is obscured by sticky evidence labels"
                        assert wrap.locator("td").first.evaluate("(e)=>getComputedStyle(e).position==='sticky'")
                        page.screenshot(path=str(OUT/f"{width}-facility-comparison-scrolled.png"),full_page=True)
                    page.get_by_role("link",name="Back to saved portfolio").click()
                    page.locator(".portfolio-count").wait_for()
                    for _ in range(2):page.get_by_role("button",name="Remove",exact=True).first.click()
                    assert "0 saved source records" in page.locator(".portfolio-count").inner_text()
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
