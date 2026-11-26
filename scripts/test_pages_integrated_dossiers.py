"""Validate integrated dossiers against the exact public source records, including unavailable sources."""
import json,os,re,statistics,subprocess,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8102/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"dossier-evidence";OUT.mkdir(exist_ok=True)
KEYS=["hospital","nursing","dialysis","home-health","hospice","rehabilitation","long-term-hospital"]
S={k:json.loads((ROOT/"web/public-directory"/(k+".json")).read_text()) for k in KEYS}
rows={k:v["records"] for k,v in S.items()}
def key(r):
    p=[" ".join(r[k].split()).upper() for k in ("address","city","state","zip")]
    return tuple(p) if all(p) else None
def capacity(r):
    v=str(r["capacity"]).strip()
    return int(v) if re.fullmatch(r"[0-9]+",v) and int(v)<=9007199254740991 else None
def fmt(x):return f"{x:,}" if x is not None else "—"
from collections import Counter
addresses=Counter(key(r) for a in rows.values() for r in a if key(r))
pair=next(r for r in rows["nursing"] if key(r) and addresses[key(r)]>1)
unmatched=next(r for r in rows["nursing"] if key(r) and addresses[key(r)]==1)
HHA=json.loads((ROOT/"web/hha-service-evidence.json").read_text())["records"]
DIA=json.loads((ROOT/"web/dialysis-service-evidence.json").read_text())["records"]
dlink=next(r for r in rows["dialysis"] if r["ccn"] in DIA)
dnone=next(r for r in rows["dialysis"] if r["ccn"] not in DIA)
hha=next(r for r in rows["home-health"] if "dash_marker" in HHA[r["state"]+":"+r["ccn"]].values())
def path(k,r,section=None,**extra):
    p={"source":k,"id":r["ccn"],"state":r["state"],**extra}
    if section:p["section"]=section
    return "#detail?"+urlencode(p)
server=subprocess.Popen(["python","-m","http.server","8102","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
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
            for k,r in [("nursing",pair),("dialysis",dlink),("dialysis",dnone),("home-health",hha),("hospital",rows["hospital"][0]),("long-term-hospital",rows["long-term-hospital"][0])]:
                page.goto(URL+path(k,r));page.locator(".dossier-evidence[data-ready=true]").wait_for()
                assert page.get_by_role("heading",name=r["name"],exact=True).count()==1
                assert page.get_by_role("navigation",name="Facility evidence sections").get_by_role("link",name="Location & peers").count()==1
                if k=="nursing":
                    assert page.get_by_role("columnheader",name="Historical citation rows").count()==1
                if k=="dialysis":
                    status="corroborated" if r["ccn"] in DIA else "unlinked"
                    assert page.locator(f".dossier-evidence .dialysis-profile[data-evidence={status}]").count()==1
                if k=="home-health":
                    assert page.locator(".dossier-evidence .hha-profile[data-evidence=qualified]").count()==1
                    actual=HHA[r["state"]+":"+r["ccn"]]
                    for field,state in actual.items():
                        assert page.locator(f'.hha-profile [data-field="{field}"] dd').inner_text()=={"yes":"Reported yes","no":"Reported no","dash_marker":"Unknown (source dash)"}[state]
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                page.screenshot(path=str(OUT/f"{width}-{k}-{r['ccn']}-dossier.png"),full_page=True)
            for r in (pair,unmatched):
                page.goto(URL+path("nursing",r))
                page.get_by_role("link",name="Location & peers",exact=True).click()
                loc=page.locator(".profile-location[data-ready=true]");loc.wait_for()
                assert loc.get_attribute("data-complete")=="true"
                expected=[(k,x) for k,rr in rows.items() for x in rr if key(x)==key(r) and not(k=="nursing" and x["ccn"]==r["ccn"] and x["state"]==r["state"])]
                assert int(loc.locator(".location-match-count").get_attribute("data-total"))==len(expected)
                if expected:
                    assert loc.locator(".profile-location-table tbody tr").count()==min(25,len(expected))
                else:assert loc.get_by_text("No other matching address tuple",exact=False).count()==1
                peers=[x for x in rows["nursing"] if x["state"]==r["state"]]
                numeric=[capacity(x) for x in peers if capacity(x) is not None]
                observed=capacity(r)
                values=loc.locator(".profile-peer-metrics .metric strong").all_inner_texts()
                median=statistics.median(numeric) if numeric else None
                expected_values=[fmt(len(peers)),fmt(len(numeric)),fmt(median)]
                if observed is not None and numeric:expected_values.append(fmt(sum(x<=observed for x in numeric)))
                assert [v.replace(".0","") if v.endswith(".0") else v for v in expected_values]==values,(values,expected_values)
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                page.screenshot(path=str(OUT/f"{width}-location-{r['ccn']}.png"),full_page=True)
                page.go_back();page.locator(".dossier-evidence[data-ready=true]").wait_for()
            page.route("**/web/public-directory/hospice.json",lambda route:route.abort())
            page.goto(URL+path("nursing",pair,"location"))
            loc=page.locator(".profile-location[data-ready=true]");loc.wait_for()
            assert loc.get_attribute("data-complete")=="false"
            assert loc.get_by_text("6 of 7 provider sources checked.",exact=False).count()==1
            assert loc.get_by_text("Partial results",exact=False).count()==1
            page.unroute("**/web/public-directory/hospice.json")
            assert not errors,errors
            page.close()
        b.close()
    print("INTEGRATED_DOSSIER_BROWSER_PASS",flush=True)
finally:
    server.terminate();server.wait(timeout=5)
