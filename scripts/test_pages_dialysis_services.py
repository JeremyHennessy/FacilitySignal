"""Validate actual public dialysis evidence, filters, profile navigation and failures."""
import hashlib,json,os,subprocess,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8097/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"dialysis-service-evidence";OUT.mkdir(exist_ok=True)
P=json.loads((ROOT/"web/dialysis-service-evidence.json").read_text())["records"]
ROWS=json.loads((ROOT/"web/public-directory/dialysis.json").read_text())["records"]
BY_ID={r["ccn"]:r for r in ROWS}
linked=next(r for r in ROWS if r["ccn"] in P)
unlinked=next(r for r in ROWS if r["ccn"] not in P)
server=subprocess.Popen(["python","-m","http.server","8097","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            with urlopen(URL,timeout=2):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError("HTTP unavailable")
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        for width in (390,768,1024,1440):
            page=b.new_page(viewport={"width":width,"height":900})
            errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
            def search(**params):
                page.goto(URL+"#dialysis-services?"+urlencode(params))
                page.locator(".dialysis-status[data-ready=true]").wait_for()
                return int(page.locator(".dialysis-status").get_attribute("data-total"))
            assert search()==2194
            assert search(field="hmdlys_srvc_sw",evidence="reported_yes")==2043
            assert search(field="prtnl_dlys_srvc_sw",evidence="reported_yes")==126
            assert search(field="home_trng_sprt_only_srvc_sw",evidence="reported_yes")==802
            assert search(field="hmdlys_srvc_sw",evidence="reported_no")==135
            assert search(field="hmdlys_srvc_sw",evidence="not_available")==16
            assert search(evidence="unlinked")==5277
            assert search(evidence="all")==7471
            assert search(field="dlys_stn_cnt",evidence="reported_count")==2178
            expected=sum(v["dlys_stn_cnt"]["state"]=="reported_count" and 10<=v["dlys_stn_cnt"]["count"]<=20 for v in P.values())
            assert search(field="dlys_stn_cnt",evidence="reported_count",min="10",max="20")==expected
            regional=sum(r["state"]=="NY" and P.get(r["ccn"],{}).get("hmdlys_srvc_sw",{}).get("state")=="reported_yes" for r in ROWS)
            assert search(state="NY",field="hmdlys_srvc_sw",evidence="reported_yes")==regional
            page.locator("select[name=state]").select_option("")
            page.get_by_role("button",name="Apply service filters").click()
            page.locator(".dialysis-status[data-ready=true]").wait_for()
            assert page.locator(".dialysis-status").get_attribute("data-total")=="2043"
            page.locator(".dialysis-results").screenshot(path=str(OUT/f"{width}-results.png"))
            page.locator(".dialysis-service-form").screenshot(path=str(OUT/f"{width}-filters.png"))
            page.locator(".dialysis-results tbody a").first.click()
            page.locator(".dialysis-profile[data-evidence=corroborated]").wait_for()
            assert page.get_by_role("link",name="Back to results",exact=True).count()==1
            page.get_by_role("link",name="Back to results",exact=True).click()
            page.locator(".dialysis-status[data-ready=true]").wait_for()
            assert page.locator(".dialysis-status").get_attribute("data-total")=="2043"
            for row,status in [(linked,"corroborated"),(unlinked,"unlinked")]:
                page.goto(URL+"#detail?"+urlencode({"source":"dialysis","id":row["ccn"],"state":row["state"],"section":"services"}))
                page.locator(f".dialysis-profile[data-evidence={status}]").wait_for()
                if status=="corroborated":
                    for field,obs in P[row["ccn"]].items():
                        labels={"reported_yes":"Reported yes","reported_no":"Reported no","not_available":"Not available"}
                        value=f'{obs["count"]:,}' if obs["state"]=="reported_count" else labels[obs["state"]]
                        assert page.locator(f'[data-field="{field}"] dd').inner_text()==value
                else:assert page.locator(".dialysis-profile-grid").count()==0
                page.locator(".dialysis-profile").screenshot(path=str(OUT/f"{width}-{status}.png"))
            page.route("**/web/dialysis-service-evidence.json?*",lambda route:route.fulfill(status=200,content_type="application/json",body="{}"))
            page.goto(URL+"#dialysis-services")
            page.get_by_text("Evidence checksum mismatch",exact=False).wait_for()
            assert page.locator(".dialysis-results").count()==0
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            assert not errors,errors
            page.close()
        b.close()
    print("DIALYSIS_SERVICE_BROWSER_PASS",flush=True)
finally:server.terminate();server.wait(timeout=5)
