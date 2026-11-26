"""Browser checks for profile evidence navigation and capacity bands on actual public data."""
import json,os,re,subprocess,time
from pathlib import Path
from urllib.parse import urlencode,urlsplit,parse_qs
from urllib.request import urlopen
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8096/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"profile-evidence"
OUT.mkdir(exist_ok=True)
def load(key):return json.loads((ROOT/f"web/public-directory/{key}.json").read_text())
def cap(row):
    text=str(row.get("capacity") if row.get("capacity") is not None else "").strip()
    return int(text) if re.fullmatch(r"[0-9]+",text) and int(text)<=9007199254740991 else None
def expected_bands(rows,source):
    ranges=[(0,0),(1,49),(50,99),(100,199),(200,None)] if source=="nursing" else [(0,0),(1,9),(10,19),(20,39),(40,None)]
    result={}
    for lo,hi in ranges:
        label=f"{lo:,}" if lo==hi else f"{lo:,}+" if hi is None else f"{lo:,}–{hi:,}"
        result[label]=sum(1 for r in rows if cap(r) is not None and cap(r)>=lo and (hi is None or cap(r)<=hi))
    result["unknown"]=sum(1 for r in rows if cap(r) is None)
    assert sum(result.values())==len(rows)
    return result

nursing=load("nursing")
dialysis=load("dialysis")
hospital=load("hospital")
sources={"nursing":nursing["records"],"dialysis":dialysis["records"]}
provider=nursing["records"][0]
server=subprocess.Popen(["python","-m","http.server","8096","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            with urlopen(URL,timeout=2):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError("local HTTP unavailable")
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        checked=[]
        for width in (390,768,1024,1440):
            page=b.new_page(viewport={"width":width,"height":900})
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            def check():
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                assert not errors,errors
            search="#facilities?"+urlencode({"source":"nursing","state":provider["state"],"field":"id","q":provider["ccn"],"sort":"name_desc","page":1})
            page.goto(URL+search)
            page.locator("tbody tr a").first.wait_for()
            page.locator("tbody tr a").first.click()
            page.get_by_role("heading",name=provider["name"],exact=True).wait_for()
            nav=page.get_by_role("navigation",name="Facility evidence sections")
            assert nav.get_by_role("link",name="Summary").get_attribute("aria-current")=="page"
            page.get_by_role("columnheader",name="Historical citation rows").wait_for()
            page.get_by_role("link",name="Services & capacity",exact=True).click()
            page.get_by_role("heading",name="Reported capacity and service evidence").wait_for()
            assert page.get_by_text("Individual QIES and iQIES service observations",exact=False).count()==1
            page.get_by_role("link",name="Sources & coverage",exact=True).click()
            page.get_by_role("heading",name="Evidence availability for this record").wait_for()
            assert page.get_by_text("Individual relationships not published",exact=True).count()==3
            assert page.get_by_role("link",name="Back to results",exact=True).get_attribute("href")==search
            page.go_back()
            page.get_by_role("heading",name="Reported capacity and service evidence").wait_for()
            page.go_forward()
            page.get_by_role("heading",name="Evidence availability for this record").wait_for()
            page.get_by_role("link",name="Back to results",exact=True).click()
            page.locator("tbody tr").first.wait_for()
            assert urlsplit(page.url).fragment==search[1:]
            assert page.locator("input[name=q]").input_value()==provider["ccn"]
            assert page.locator("select[name=sort]").input_value()=="name_desc"
            # Explicit route and no unsafe return destination.
            h=hospital["records"][0]
            page.goto(URL+"#detail?"+urlencode({"source":"hospital","id":h["ccn"],"state":h["state"],"section":"compliance","return":"https://example.test/"}))
            page.get_by_text("does not contain facility-linked inspection",exact=False).wait_for()
            assert page.get_by_role("link",name="Back to directory").get_attribute("href").startswith("#facilities?")
            check()
            for source,state in [("nursing",None),("dialysis","NY")]:
                params={"source":source}
                if state:params["state"]=state
                page.goto(URL+"#capacity?"+urlencode(params))
                page.locator(".capacity-band").first.wait_for()
                rows=[r for r in sources[source] if state is None or r["state"]==state]
                expect=expected_bands(rows,source)
                actual={e.get_attribute("data-band"):int(e.locator("strong").inner_text().replace(",","")) for e in page.locator(".capacity-band").all()}
                assert actual==expect,(source,width,actual,expect)
                band=page.locator('.capacity-band[data-band="1–49"]' if source=="nursing" else '.capacity-band[data-band="10–19"]')
                expected_count=expect["1–49" if source=="nursing" else "10–19"]
                band.click()
                page.locator(".capacity-band").first.wait_for()
                assert int(page.locator(".metrics .metric strong").first.inner_text().replace(",",""))==expected_count
                lo,hi=(1,49) if source=="nursing" else (10,19)
                assert page.locator("input[name=min]").input_value()==str(lo)
                assert page.locator("input[name=max]").input_value()==str(hi)
                assert all(lo<=int(v.replace(",",""))<=hi for v in page.locator(".table-wrap").first.locator("tbody tr td:nth-child(3)").all_inner_texts())
                check()
            page.goto(URL+"#capacity?source=nursing&min=100&max=10")
            page.get_by_text("Minimum capacity cannot exceed maximum capacity",exact=False).wait_for()
            page.goto(URL+"#detail?"+urlencode({"source":"nursing","id":provider["ccn"],"state":provider["state"],"section":"sources"}))
            page.get_by_role("heading",name="Evidence availability for this record").wait_for()
            check()
            # Public provider projection only, no new restricted data.
            page.screenshot(path=str(OUT/f"{width}-profile-sources.png"),full_page=True)
            checked.append({"width":width,"profile_sections":True,"return_state":True,"capacity_distribution":True})
            page.close()
        b.close()
    (OUT/"report.json").write_text(json.dumps({"public_projection_only":True,"checks":checked},indent=2))
    print("PROFILE_CAPACITY_BROWSER_PASS",json.dumps(checked),flush=True)
finally:
    server.terminate();server.wait(timeout=5)
