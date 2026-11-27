"""Browser qualification of the actual archive-derived public institutional pack.
Screenshots show public CMS records only; JPEG chunks permit visual inspection
through the normal GitHub job log when artifact transfer is unavailable.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
from scripts.stage_institutional_public_candidate import manifest_for, FIELDS

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"institutional-browser-evidence"
OUT.mkdir(exist_ok=True)
PUBLIC="https://jeremyhennessy.github.io/FacilitySignal/"
LOCAL="http://127.0.0.1:8099/"
META=json.loads((ROOT/"web/institutional-evidence-manifest.json").read_text())
assert META==manifest_for(ROOT/"web")
PACK=json.loads((ROOT/"web/institutional-evidence.json").read_text())["sources"]
DATA={s:json.loads((ROOT/"web/public-directory"/(s+".json")).read_text())["records"] for s in FIELDS}
OBS={s:{(r[0],r[1]):dict(zip(FIELDS[s],r[2:])) for r in PACK[s]["records"]} for s in FIELDS}
COMPARE_LABELS={"emergency_services":"Emergency services","chain_owned_or_managed":"Chain owned or managed","late_shift":"Shift starting at 5 p.m. or later","in_center_hemodialysis":"In-center hemodialysis","peritoneal_dialysis":"Peritoneal dialysis","home_hemodialysis_training":"Home hemodialysis training","ownership_change_12_months":"Ownership change in preceding 12 months"}
HASHES={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ("index.html","web/pages.js","web/pages.css","web/institutional-evidence.json")}
def digest(b):return hashlib.sha256(b).hexdigest()
def expected(source,field,value,state=""):
    return [r for r in DATA[source] if (not state or r["state"]==state) and OBS[source][(r["ccn"],r["state"])][field]==value]
def results(page,n):
    status=page.locator('.advanced-status[data-complete="true"]')
    status.wait_for(timeout=30000)
    assert int(status.get_attribute("data-total"))==n
    assert page.locator(".advanced-results tbody tr").count()==min(25,n)
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
def capture(page,name,target):
    target.scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/(name+".jpg")),type="jpeg",quality=64,animations="disabled")
def entry(browser,base,utm,live):
    for i in range(30 if live else 1):
        ctx=browser.new_context(viewport={"width":1440,"height":900})
        p=ctx.new_page();responses=[];p.on("response",lambda r:responses.append(r))
        try:
            res=p.goto(base+utm+"#advanced?source=hospital&institutional_field=emergency_services&institutional_value=reported_yes&run=1",wait_until="load",timeout=30000)
            assert res and res.status==200 and digest(res.body())==HASHES["index.html"],"stale entry point"
            results(p,4501)
            for path in ("web/pages.js","web/pages.css","web/institutional-evidence.json"):
                version=base+path+"?v="+HASHES[path][:16]
                seen=[r for r in responses if r.url==version]
                assert seen and digest(seen[-1].body())==HASHES[path],"stale browser asset "+path
            p.reload(wait_until="load");results(p,4501)
            return {"url":base+utm,"warm_reload":True,"verified_asset_hashes":HASHES}
        except Exception:
            if not live or i==29:raise
            time.sleep(5)
        finally:ctx.close()
def service_topics(page,base,width):
    page.goto(base+"#services")
    nav=page.get_by_role("navigation",name="National iQIES evidence topics")
    panel=page.locator(".service-topic-panel")
    groups=page.locator(".intelligence-table")
    assert nav.get_by_role("link",name="All service evidence").get_attribute("aria-current")=="page"
    assert groups.count()==10
    asc=nav.get_by_role("link",name="ASC surgery indicators")
    asc.focus();asc.press("Enter")
    page.get_by_role("heading",name="ASC surgical specialty evidence",exact=True).wait_for()
    assert urlsplit(page.url).fragment=="services?topic=asc"
    assert asc.get_attribute("aria-current")=="page" and groups.count()==1
    assert groups.locator("tbody tr").count()==8
    assert groups.locator("tbody tr").first.locator("td").all_inner_texts()==["8,492","2,293","5,747","452"]
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    capture(page,f"{width}-service-topic-asc",panel)
    groups.screenshot(path=str(OUT/f"{width}-service-topic-asc-table.jpg"),type="jpeg",quality=64,animations="disabled")
    page.goto(base+"#services?topic=dialysis")
    page.get_by_role("heading",name="Dialysis commencement and continuation evidence",exact=True).wait_for()
    assert nav.get_by_role("link",name="Dialysis indicators").get_attribute("aria-current")=="page"
    assert groups.count()==1 and groups.locator("tbody tr").count()==3
    assert groups.locator("tbody tr").first.locator("td").all_inner_texts()==["8,659","12","8,435","212"]
    assert "does not mean the service was absent" in panel.inner_text()
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    capture(page,f"{width}-service-topic-dialysis",panel)
    groups.screenshot(path=str(OUT/f"{width}-service-topic-dialysis-table.jpg"),type="jpeg",quality=64,animations="disabled")
    page.go_back()
    asc.and_(page.locator("[aria-current=page]")).wait_for()
    page.go_forward()
    nav.get_by_role("link",name="Dialysis indicators").and_(page.locator("[aria-current=page]")).wait_for()
    page.goto(base+"#services?topic=unknown")
    page.get_by_text("That service topic is unavailable. Showing all service evidence.",exact=True).wait_for()
    assert groups.count()==10
    page.route("**/web/public-intelligence.json",lambda route:route.fulfill(status=503,body=""))
    page.goto(base+"#services?topic=asc")
    page.get_by_text("Qualified aggregate evidence unavailable:",exact=False).wait_for()
    assert groups.count()==0
    page.unroute("**/web/public-intelligence.json")
def ltch_source_handoff(page,base,width):
    provider=base+"#detail?source=long-term-hospital&id=012006&state=AL"
    requests=[]
    def observe(request):
        if (urlsplit(request.url).hostname or "").endswith("medicare.gov"):
            requests.append(request.url)
    page.on("request",observe)
    page.goto(provider)
    nav=page.get_by_role("navigation",name="Facility evidence sections")
    nav.get_by_role("link",name="Sources & coverage").click()
    card=page.locator(".ltch-quality-source[data-evidence='source-link']")
    link=card.get_by_role("link",name="Open this provider’s quality evidence on Medicare.gov")
    assert link.get_attribute("href")=="https://www.medicare.gov/care-compare/details/long-term-care/012006/view-all"
    assert link.get_attribute("target")=="_blank" and link.get_attribute("referrerpolicy")=="no-referrer"
    assert set(link.get_attribute("rel").split())=={"noopener","noreferrer"}
    assert "does not load or republish these scores" in card.inner_text()
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    capture(page,f"{width}-ltch-quality-publisher",card)
    page.go_back()
    assert not page.locator(".ltch-quality-source").count()
    page.go_forward();link.wait_for()
    page.goto(provider.replace("state=AL","state=DC")+"&section=sources")
    page.get_by_text("No matching source record returned.",exact=True).wait_for()
    assert not page.locator(".ltch-quality-source").count()
    url="**/web/public-directory/long-term-hospital.json*"
    altered=json.loads((ROOT/"web/public-directory/long-term-hospital.json").read_text())
    next(r for r in altered["records"] if r["ccn"]=="012006")["address"]="Unverified fixture address"
    page.route(url,lambda route:route.fulfill(status=200,json=altered))
    page.goto(provider+"&section=sources")
    page.locator(".ltch-quality-source[data-evidence='unavailable']").wait_for()
    assert not page.locator(".ltch-quality-source a").count()
    page.unroute(url)
    page.remove_listener("request",observe)
    assert not requests,"Medicare requested without user clicking the link"
def run(base,live):
    summary=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        entries=[entry(browser,base,q,live) for q in ("","?utm_source=chatgpt.com")]
        for width in (390,768,1024,1440):
            ctx=browser.new_context(viewport={"width":width,"height":900},accept_downloads=True)
            page=ctx.new_page();errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(base+"#advanced")
            page.locator("select[name=source]").wait_for()
            assert page.locator("select[name=institutional_field]").is_disabled()
            page.locator("select[name=source]").select_option("dialysis")
            page.locator("select[name=state]").select_option("NY")
            page.locator("select[name=institutional_field]").select_option("late_shift")
            page.locator("select[name=institutional_value]").select_option("reported_yes")
            page.get_by_role("button",name="Apply search filters").click()
            want=expected("dialysis","late_shift","reported_yes","NY")
            results(page,len(want))
            assert page.get_by_role("columnheader",name="Institutional evidence").count()==1
            assert set(page.locator(".advanced-results tbody tr td:nth-last-child(2)").all_inner_texts())=={"Reported yes"}
            capture(page,f"{width}-filters",page.locator("select[name=institutional_field]"))
            with page.expect_download() as info:page.get_by_role("button",name="Export current page (CSV)").click()
            rows=list(csv.DictReader(io.StringIO(info.value.path().read_text())))
            assert len(rows)==min(25,len(want))
            assert all(r["state"]=="NY" and r["institutional_field"]=="late_shift" and r["institutional_value"]=="reported_yes" and r["institutional_release"]==PACK["dialysis"]["release"] and OBS["dialysis"][(r["ccn"],r["state"])]["late_shift"]=="reported_yes" for r in rows)
            origin=urlsplit(page.url).fragment
            if len(want)>25:
                page.get_by_role("link",name="Next",exact=True).click()
                assert page.locator("select[name=institutional_field]").input_value()=="late_shift"
                assert page.locator('.advanced-status[data-complete=true]').get_attribute("data-total")==str(len(want))
                page.go_back();results(page,len(want))
            page.locator(".advanced-results tbody tr a").first.click()
            profile=page.locator(".institutional-profile[data-evidence=qualified]");profile.wait_for(timeout=30000)
            assert profile.locator("[data-field]").count()==5
            assert profile.locator('[data-field="late_shift"] dd').inner_text()=="Reported yes"
            capture(page,f"{width}-profile",profile)
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.get_by_role("link",name="Back to results").click();results(page,len(want))
            assert urlsplit(page.url).fragment==origin
            for source,fields in FIELDS.items():
                for field in fields:
                    value="reported_yes"
                    url=base+"#advanced?"+urlencode({"source":source,"institutional_field":field,"institutional_value":value,"run":1})
                    page.goto(url);results(page,len(expected(source,field,value)))
                    assert page.locator("select[name=institutional_field]").input_value()==field
                    assert page.locator("select[name=institutional_field]").evaluate("""e=>{const c=getComputedStyle(e),x=document.createElement('canvas').getContext('2d');x.font=c.font;return x.measureText(e.selectedOptions[0].text).width+parseFloat(c.paddingLeft)+parseFloat(c.paddingRight)+24<=e.clientWidth+1}"""),(width,source,field)
            page.goto(base+"#advanced?source=dialysis&institutional_field=late_shift&institutional_value=reported_no&run=1");results(page,6335)
            page.goto(base+"#advanced?source=nursing&institutional_field=sprinklers&institutional_value=reported_yes&run=1")
            page.get_by_text("Choose an institutional characteristic",exact=False).wait_for()
            chosen=[(s,DATA[s][0]) for s in ("hospital","dialysis","nursing")]
            for source,r in chosen:
                page.goto(base+"#detail?"+urlencode({"source":source,"id":r["ccn"],"state":r["state"]}))
                page.get_by_role("button",name="Save to research portfolio").click()
            page.get_by_role("link",name="Open saved portfolio").click()
            for i in range(3):page.locator(".portfolio-provider-cell input").nth(i).check()
            page.get_by_role("button",name="Compare selected (3 / 4)").click()
            comparison=page.locator(".comparison-table[data-records='3']")
            comparison.wait_for()
            compare_url=page.url
            def comparison_rows():
                return {cells[0]:cells[1:] for cells in [tr.locator("td").all_inner_texts() for tr in comparison.locator("tbody tr").all()]}
            compare_rows=comparison_rows()
            assert compare_rows["Institutional evidence release"]==[PACK[s]["release"] for s,r in chosen]
            for field,label in COMPARE_LABELS.items():
                expected_values=[("Reported yes" if OBS[s][(r["ccn"],r["state"])][field]=="reported_yes" else "Reported no") if field in FIELDS[s] else "Not applicable to this source" for s,r in chosen]
                assert compare_rows[label+" (reported)"]==expected_values,(width,field)
            with page.expect_download() as info:page.get_by_role("button",name="Export comparison CSV").click()
            matrix=list(csv.reader(io.StringIO(info.value.path().read_text())))
            exported={row[0]:row[1:] for row in matrix[1:]}
            assert all(exported[label+" (reported)"]==compare_rows[label+" (reported)"] for label in COMPARE_LABELS.values())
            assert exported["Institutional evidence release"]==compare_rows["Institutional evidence release"]
            assert all("not current service availability" in x for x in exported["Evidence limitations"])
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.screenshot(path=str(OUT/f"{width}-institutional-comparison.png"),full_page=True,animations="disabled")
            evidence_row=comparison.locator("tbody tr").filter(has_text="Emergency services (reported)")
            evidence_row.scroll_into_view_if_needed()
            page.screenshot(path=str(OUT/f"{width}-institutional-rows.png"),animations="disabled")
            if comparison.evaluate("(e)=>e.scrollWidth>e.clientWidth+1"):
                assert comparison.evaluate("(e)=>{e.scrollLeft=e.scrollWidth;const f=e.getBoundingClientRect();return e.scrollLeft>0&&Array.from(e.querySelectorAll('tr')).every(tr=>{const first=tr.cells[0].getBoundingClientRect(),last=tr.cells[tr.cells.length-1].getBoundingClientRect();return getComputedStyle(tr.cells[0]).position==='sticky'&&first.left>=f.left-2&&first.left<=f.left+2&&last.left>=first.right-2&&last.right<=f.right+2})}"),"Comparison labels or final provider clipped"
                page.screenshot(path=str(OUT/f"{width}-institutional-rows-scrolled.png"),animations="disabled")
                page.screenshot(path=str(OUT/f"{width}-institutional-comparison-scrolled.png"),full_page=True,animations="disabled")
            page.route("**/web/institutional-evidence.json*",lambda route:route.fulfill(status=200,body="{}"))
            page.reload();comparison.wait_for()
            invalid_rows=comparison_rows()
            assert invalid_rows["Institutional evidence release"]==["Qualified institutional evidence unavailable"]*3
            assert "3 exact published records resolved" in page.locator(".comparison-status").inner_text()
            for field,label in COMPARE_LABELS.items():
                assert invalid_rows[label+" (reported)"]==["Qualified institutional evidence unavailable" if field in FIELDS[s] else "Not applicable to this source" for s,r in chosen]
            assert page.url==compare_url

            page.goto(base+"#advanced?source=hospital&institutional_field=emergency_services&institutional_value=reported_yes&run=1")
            page.locator('.advanced-status[data-complete=false]').wait_for()
            assert "Partial results" in page.locator(".advanced-status").inner_text()
            assert not page.get_by_role("button",name="Export current page (CSV)").count()
            page.unroute("**/web/institutional-evidence.json*")
            service_topics(page,base,width)
            ltch_source_handoff(page,base,width)
            assert not errors,errors
            summary.append({"width":width,"dialysis_NY_late_shift":len(want),"positive_negative_and_exact_filters":True,"private_field_rejected":True,"bad_pack_unavailable":True,"csv_and_return":True,"institutional_comparison_all_seven_and_csv":True,"comparison_bad_pack_preserves_basic_records":True,"sticky_evidence_labels_and_final_provider":True,"national_iqies_topics_counts_history_and_error":True,"ltch_exact_href_no_external_fetch_and_drift_block":True})
            ctx.close()
        browser.close()
    report={"mode":"ordinary_live" if live else "candidate","entry_checks":entries,"viewport_checks":summary}
    (OUT/"report.json").write_text(json.dumps(report,indent=2))
    print("FACILITYSIGNAL_INSTITUTIONAL_BROWSER_PASS",json.dumps(report,sort_keys=True),flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--live",action="store_true");a=parser.parse_args()
    server=None
    if not a.live:
        server=subprocess.Popen(["python","-m","http.server","8099","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                with urlopen(LOCAL,timeout=2):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError("local HTTP unavailable")
    try:run(PUBLIC if a.live else LOCAL,a.live)
    finally:
        if server:server.terminate();server.wait(timeout=5)

if __name__=="__main__":main()
