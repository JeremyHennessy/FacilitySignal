"""Actual public projection tests; no new publisher downloads."""
import csv,io,json,os,re,subprocess,time
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8099/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"advanced-research-evidence"
OUT.mkdir(exist_ok=True)
manifest=json.loads((ROOT/"web/public-directory/manifest.json").read_text())
sources={k:json.loads((ROOT/f"web/public-directory/{k}.json").read_text()) for k in manifest["sources"] if not k.startswith("nursing-")}
def cap(r):
    v=str(r.get("capacity") if r.get("capacity") is not None else "").strip()
    return int(v) if re.fullmatch(r"\d+",v) and int(v)<=9007199254740991 else None
expected=[r for r in sources["nursing"]["records"] if r["state"]=="NY" and cap(r) is not None and 100<=cap(r)<=199]
expected_all=sum(sum(r["state"]=="VT" for r in d["records"]) for d in sources.values())
server=subprocess.Popen(["python","-m","http.server","8099","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
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
            ctx=b.new_context(viewport={"width":width,"height":900},accept_downloads=True)
            page=ctx.new_page();errors=[];requests=[]
            page.on("pageerror",lambda e:errors.append(str(e)));page.on("request",lambda req:requests.append(req.url))
            start=time.perf_counter();page.goto(URL+"#geography")
            page.locator(".market-region").first.wait_for()
            assert page.locator('[data-aggregation="precomputed"]').count()==1
            assert not any(re.search(r"/public-directory/(?!manifest)[a-z-]+\.json",u) for u in requests),requests
            assert page.locator(".market-region").count()==56
            map_ms=round((time.perf_counter()-start)*1000,1)
            page.goto(URL+"#advanced")
            assert page.locator("input[name=min]").is_disabled()
            page.locator("select[name=source]").select_option("nursing")
            page.locator("select[name=state]").select_option("NY")
            page.locator("input[name=min]").fill("100")
            page.locator("input[name=max]").fill("199")
            page.get_by_role("button",name="Apply search filters").click()
            page.locator('.advanced-status[data-complete="true"]').wait_for()
            assert int(page.locator(".advanced-status").get_attribute("data-total"))==len(expected)
            assert page.locator("tbody tr").count()==min(25,len(expected))
            assert all(100<=int(x.split()[0].replace(",",""))<=199 for x in page.locator("tbody tr td:nth-child(4)").all_inner_texts())
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.evaluate("window.scrollTo(0,0)")
            page.screenshot(path=str(OUT/f"{width}-advanced.png"),full_page=False)
            page.locator(".advanced-form").screenshot(path=str(OUT/f"{width}-advanced-filters.png"))
            page.locator(".advanced-results").screenshot(path=str(OUT/f"{width}-advanced-results.png"))
            if width==1440:
                assert page.locator("select[name=field]").evaluate("(e)=>e.getBoundingClientRect().width>=220")
                assert page.locator("input[name=max]").evaluate("(e)=>e.getBoundingClientRect().width<400")
            if width==390:
                assert page.locator(".advanced-results").evaluate("(e)=>e.scrollWidth>e.clientWidth")
            with page.expect_download() as info:page.get_by_role("button",name="Export current page (CSV)").click()
            exported=list(csv.DictReader(io.StringIO(info.value.path().read_text())))
            assert len(exported)==min(25,len(expected))
            assert all(x["source"]=="nursing" and x["state"]=="NY" and x["capacity_unit"]=="Certified beds" and 100<=int(x["reported_numeric_capacity"])<=199 for x in exported)
            origin=urlsplit(page.url).fragment
            page.locator("tbody tr a").first.click()
            page.get_by_role("link",name="Back to results").wait_for()
            page.get_by_role("link",name="Back to results").click()
            page.locator('.advanced-status[data-complete="true"]').wait_for()
            assert urlsplit(page.url).fragment==origin
            page.goto(URL+"#advanced?source=all&state=VT&run=1")
            page.locator('.advanced-status[data-complete="true"]').wait_for()
            assert int(page.locator(".advanced-status").get_attribute("data-total"))==expected_all
            page.get_by_role("link",name="Next",exact=True).click()
            page.locator('.advanced-status[data-complete="true"]').wait_for()
            page.get_by_text("Page 2 ·",exact=False).wait_for()
            page.goto(URL+"#advanced?source=all&min=1&run=1")
            page.get_by_text("Choose one capacity-qualified category",exact=False).wait_for()
            page.goto(URL+"#industry?state=NY")
            page.get_by_role("heading",name="Water treatment & dialysis").wait_for()
            assert page.locator(".industry-panel").count()==6
            page.screenshot(path=str(OUT/f"{width}-industry.png"),full_page=False)
            page.get_by_role("link",name="Dialysis providers",exact=True).click()
            page.locator('.advanced-status[data-complete="true"]').wait_for()
            assert int(page.locator(".advanced-status").get_attribute("data-total"))==sum(r["state"]=="NY" for r in sources["dialysis"]["records"])
            # Minnesota-only referral: no source traffic from viewing the card, no provider data sent to DLI.
            page.goto(URL+"#industry")
            pathway=page.get_by_role("heading",name="Minnesota boiler registration research")
            pathway.wait_for(state="hidden")
            page.locator("select[name=state]").select_option("MN")
            start=len(requests)
            page.get_by_role("button",name="Apply jurisdiction").click()
            pathway.wait_for()
            card=page.locator(".industry-panel").filter(has=pathway)
            assert "Equipment is not linked" in card.inner_text()
            campus_scope="CMS provider records are not a full list of physical campuses."
            assert card.get_by_text(campus_scope,exact=False).is_visible()
            assert "A certificate for one address does not verify equipment at another campus." in card.inner_text()
            assert "requires an account" in card.inner_text()
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            card.screenshot(path=str(OUT/f"{width}-industry-minnesota-boiler.png"))
            assert not requests[start:],requests[start:]
            official=card.get_by_role("link",name="Minnesota DLI certificate lookup instructions",exact=False)
            assert official.get_attribute("href")=="https://dli.mn.gov/workers/boiler-engineer/certificate-registration-boilers-and-pressure-vessels"
            assert official.get_attribute("target")=="_blank" and set(official.get_attribute("rel").split())=={"noopener","noreferrer"}
            mn_counts={source:sum(r["state"]=="MN" for r in sources[source]["records"]) for source in ("hospital","nursing")}
            for source,records in mn_counts.items():
                assert records>0
                start=len(requests)
                card.get_by_role("link",name=f"Minnesota {source} provider records").click()
                page.locator('.advanced-status[data-complete="true"]').wait_for()
                assert urlsplit(page.url).fragment==f"advanced?source={source}&state=MN&run=1"
                assert int(page.locator(".advanced-status").get_attribute("data-total"))==records
                assert all(urlsplit(u).netloc==urlsplit(URL).netloc for u in requests[start:]),requests[start:]
                assert all(urlsplit(u).path.rsplit("/",1)[-1] in ("manifest.json",f"{source}.json") for u in requests[start:]),requests[start:]
                page.go_back()
                assert urlsplit(page.url).fragment=="industry?state=MN"
                pathway.wait_for()
            page.go_forward()
            page.locator('.advanced-status[data-complete="true"]').wait_for()
            assert int(page.locator(".advanced-status").get_attribute("data-total"))==mn_counts["nursing"]
            page.go_back()
            pathway.wait_for()
            page.locator("select[name=state]").select_option("NY")
            page.get_by_role("button",name="Apply jurisdiction").click()
            page.wait_for_function("location.hash === '#industry?state=NY'")
            pathway.wait_for(state="hidden")
            page.goto(URL+"?utm_source=chatgpt.com#industry?state=MN")
            assert card.get_by_text(campus_scope,exact=False).is_visible()
            page.reload()
            assert card.get_by_text(campus_scope,exact=False).is_visible()
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            card.screenshot(path=str(OUT/f"{width}-industry-minnesota-boiler-warm.png"))
            # Market and quick-search handoffs retain the exact selection and support back/forward.
            page.goto(URL+"#geography?source=hospital&state=NY")
            page.locator(".market-region[data-state=NY][aria-current=true]").wait_for()
            page.get_by_role("link",name="Search this market with advanced filters").click()
            page.locator('.advanced-status[data-complete="true"]').wait_for()
            assert page.locator("select[name=source]").input_value()=="hospital"
            assert page.locator("select[name=state]").input_value()=="NY"
            assert int(page.locator(".advanced-status").get_attribute("data-total"))==sum(r["state"]=="NY" for r in sources["hospital"]["records"])
            page.wait_for_function("window.scrollY<=1")
            page.go_back()
            page.locator(".market-region[data-state=NY][aria-current=true]").wait_for()
            page.go_forward()
            page.locator('.advanced-status[data-complete="true"]').wait_for()
            page.goto(URL+"#geography?source=all&state=VT")
            page.locator(".market-region[data-state=VT][aria-current=true]").wait_for()
            page.get_by_role("link",name="Search this market with advanced filters").click()
            page.locator('.advanced-status[data-complete="true"]').wait_for()
            assert int(page.locator(".advanced-status").get_attribute("data-total"))==expected_all
            sample=next(r for r in sources["nursing"]["records"] if r["state"]=="NY")
            term=sample["ccn"]
            page.goto(URL+"#search?"+urlencode({"field":"id","q":term,"state":"NY"}))
            page.locator('.unified-status[data-complete="true"]').wait_for()
            wrap=page.locator(".unified-search-results").first
            assert wrap.evaluate("(e)=>Array.from(e.querySelectorAll('th:nth-child(n+3),td:nth-child(n+3)')).every(c=>getComputedStyle(c).whiteSpace==='nowrap')")
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            if wrap.evaluate("(e)=>e.scrollWidth>e.clientWidth+1"):
                assert wrap.evaluate("(e)=>{e.scrollLeft=e.scrollWidth;const t=e.querySelector('tbody tr td:last-child');return e.scrollLeft>0&&t.getBoundingClientRect().right<=e.getBoundingClientRect().right+2}")
                wrap.evaluate("(e)=>{e.scrollLeft=0}")
            page.get_by_role("link",name="Refine and export matching facilities").click()
            page.locator('.advanced-status[data-complete="true"]').wait_for()
            assert page.locator("select[name=field]").input_value()=="id"
            assert page.locator("input[name=q]").input_value()==term
            assert page.locator("select[name=state]").input_value()=="NY"
            expected_ccn=sum(sum(r["state"]=="NY" and r["ccn"].lower()==term.lower() for r in d["records"]) for d in sources.values())
            assert int(page.locator(".advanced-status").get_attribute("data-total"))==expected_ccn
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.screenshot(path=str(OUT/f"{width}-search-handoff.png"),full_page=True)
            page.go_back()
            page.locator('.unified-status[data-complete="true"]').wait_for()
            page.screenshot(path=str(OUT/f"{width}-quick-search-handoff.png"),full_page=True)
            # Missing/invalid aggregate must not turn into a false zero map.
            page.route("**/web/market-summary.json*",lambda route:route.fulfill(status=503,body="unavailable"))
            requests.clear();page.goto(URL+"#geography?source=hospital&state=NY")
            page.locator(".market-region").first.wait_for()
            assert page.locator('[data-aggregation="source-shard-fallback"]').count()==1
            assert any(re.search(r"/public-directory/(?!manifest)[a-z-]+\.json",u) for u in requests)
            assert not errors,errors
            checks.append({"width":width,"map_render_ms":map_ms,"nursing_matches":len(expected),"vermont_matches":expected_all,"export_and_return_state":True,"industry_links":True,"minnesota_boiler_referral":mn_counts,"aggregate_fallback":True})
            ctx.close()
        b.close()
    (OUT/"report.json").write_text(json.dumps({"checks":checks},indent=2))
    print("ADVANCED_RESEARCH_BROWSER_PASS",json.dumps(checks),flush=True)
finally:server.terminate();server.wait(timeout=5)
