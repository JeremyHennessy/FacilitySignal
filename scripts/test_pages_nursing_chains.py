"""Exercise exact CMS chain membership research on actual public records."""
import csv,io,json,os,subprocess,time
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8106/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"chain-browser-evidence";OUT.mkdir(exist_ok=True)
pack=json.loads((ROOT/"web/nursing-chain-evidence.json").read_text())
directory=json.loads((ROOT/"web/public-directory/nursing.json").read_text())["records"]
by={(r["ccn"],r["state"]):r for r in directory}
groups={r[0]:(r[1],r[2]) for r in pack["groups"]}
membership={(c,s):cid for c,s,cid in pack["members"]}
group=max(groups,key=lambda cid:groups[cid][1])
members=[by[k] for k,cid in membership.items() if cid==group]
state=members[0]["state"]
expected=[r for r in members if r["state"]==state]
fixture=expected[0];unknown=next(by[k] for k,cid in membership.items() if cid is None)
def profile(r):
    return "#detail?"+urlencode({"source":"nursing","id":r["ccn"],"state":r["state"]})
def scope(page,n):
    loc=page.locator(".chain-explorer[data-ready=true]");loc.wait_for(timeout=30000)
    assert loc.locator(".chain-status").get_attribute("data-total")==str(n)
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
    return loc
server=subprocess.Popen(["python","-m","http.server","8106","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            with urlopen(URL,timeout=2):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError("HTTP unavailable")
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        for width in (390,768,1024,1440):
            ctx=b.new_context(viewport={"width":width,"height":900},accept_downloads=True)
            page=ctx.new_page();errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(URL+"#nursing-portfolios")
            loc=scope(page,612)
            assert loc.locator(".chain-groups tbody tr").count()==25
            loc.screenshot(path=str(OUT/f"{width}-group-directory.png"))
            loc.locator("input[name=chain_q]").fill(groups[group][0])
            loc.get_by_role("button",name="Find groups").click()
            loc=scope(page,sum(name.lower().find(groups[group][0].lower())>=0 for name,_ in groups.values()))
            loc.locator(".chain-groups").get_by_role("link",name=groups[group][0],exact=True).click()
            loc=scope(page,len(members))
            assert loc.locator(".chain-members tbody tr").count()==min(25,len(members))
            loc.locator("select[name=chain_state]").select_option(state)
            loc.get_by_role("button",name="Filter members").click()
            loc=scope(page,len(expected))
            actual=loc.locator(".metrics .metric strong").all_inner_texts()
            known=[int(r["capacity"]) for r in expected if str(r["capacity"]).strip().isdigit()]
            assert actual==[f"{len(members):,}",f"{len(expected):,}",f"{sum(known):,}" if known else "—","1"],actual
            loc.screenshot(path=str(OUT/f"{width}-group-detail.png"))
            with page.expect_download() as dl:loc.get_by_role("button",name="Export matching members (CSV)").click()
            records=list(csv.DictReader(io.StringIO(dl.value.path().read_text())))
            assert {(r["ccn"],r["state"]) for r in records}=={(r["ccn"],r["state"]) for r in expected}
            assert all(r["cms_chain_id"]==group and r["release"]==pack["release"] for r in records)
            origin=urlsplit(page.url).fragment
            loc.locator(".chain-members tbody tr a").first.click()
            prof=page.locator(".nursing-chain-profile[data-evidence=assigned]");prof.wait_for(timeout=30000)
            assert prof.get_by_role("link",name=groups[group][0],exact=True).count()==1
            prof.screenshot(path=str(OUT/f"{width}-member-profile.png"))
            assert page.get_by_role("link",name="Back to results").get_attribute("href")=="#"+origin
            page.get_by_role("link",name="Back to results").click();scope(page,len(expected))
            page.goto(URL+profile(unknown))
            page.locator(".nursing-chain-profile[data-evidence=unassigned]").wait_for()
            assert page.get_by_text("does not establish that the facility is independent",exact=False).count()==1
            page.goto(URL+"#nursing-portfolios?chain_q=NO_SUCH_GROUP_ZZZZZ")
            scope(page,0)
            page.route("**/web/nursing-chain-evidence.json?*",lambda route:route.fulfill(status=200,content_type="application/json",body='{}'))
            page.goto(URL+"#nursing-portfolios?chain="+group)
            page.locator(".chain-explorer[data-ready=false] .error").wait_for()
            assert page.locator(".chain-members").count()==0
            page.goto(URL+profile(fixture))
            page.locator(".nursing-chain-profile[data-evidence=unavailable]").wait_for()
            assert not errors,errors
            ctx.close()
        b.close()
    print("NURSING_CHAIN_BROWSER_PASS",flush=True)
finally:
    server.terminate();server.wait(timeout=5)
