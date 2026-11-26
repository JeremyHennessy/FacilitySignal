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
                for field in (fields if width==1440 else fields[:1]):
                    value="reported_yes"
                    url=base+"#advanced?"+urlencode({"source":source,"institutional_field":field,"institutional_value":value,"run":1})
                    page.goto(url);results(page,len(expected(source,field,value)))
                    assert page.locator("select[name=institutional_field]").input_value()==field
            page.goto(base+"#advanced?source=dialysis&institutional_field=late_shift&institutional_value=reported_no&run=1");results(page,6335)
            page.goto(base+"#advanced?source=nursing&institutional_field=sprinklers&institutional_value=reported_yes&run=1")
            page.get_by_text("Choose an institutional characteristic",exact=False).wait_for()
            page.route("**/web/institutional-evidence.json*",lambda route:route.fulfill(status=200,body="{}"))
            page.goto(base+"#advanced?source=hospital&institutional_field=emergency_services&institutional_value=reported_yes&run=1")
            page.locator('.advanced-status[data-complete=false]').wait_for()
            assert "Partial results" in page.locator(".advanced-status").inner_text()
            assert not page.get_by_role("button",name="Export current page (CSV)").count()
            page.unroute("**/web/institutional-evidence.json*")
            assert not errors,errors
            summary.append({"width":width,"dialysis_NY_late_shift":len(want),"positive_negative_and_exact_filters":True,"private_field_rejected":True,"bad_pack_unavailable":True,"csv_and_return":True})
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
