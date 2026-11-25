"""Real Chromium qualification against synthetic QA data only."""
import argparse, concurrent.futures, json, statistics, subprocess, sys, time
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

WIDTHS=(390,768,1024,1440)
BASE={"overview":"/","facilities":"/facilities","facility":"/facility?dataset=hospital&ccn=000001","citations":"/findings","hospital-surveys":"/hospital-surveys","certifications":"/certifications","sources":"/sources"}
EXTRA={"search":"/search?q=000001&mode=identifier","certification-detail":"/certification?registry=qies&row=1","ownership-coverage":"/ownership-coverage"}
TARGETS={"/api/search?q=000001&mode=identifier":1000,"/api/search?q=Synthetic+hospital":3000,"/api/overview":3000,"/api/facilities?state=AL&sort=name_desc&limit=25":1000}
@contextmanager
def server(root,db,port):
    url=f"http://127.0.0.1:{port}"
    p=subprocess.Popen([sys.executable,str(root/"facilitysignal.py"),"--db",str(db),"serve","--port",str(port)],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with urlopen(url+"/styles.css",timeout=2) as response:
                    if response.status==200:break
            except OSError:time.sleep(.1)
        else:raise RuntimeError("local server not ready")
        yield url
    finally:
        p.terminate()
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:p.kill();p.wait()

def hit(url,path):
    start=time.perf_counter()
    with urlopen(url+path,timeout=30) as response:
        assert response.status==200,path
        data=json.load(response)
    return round((time.perf_counter()-start)*1000,2),data

def capture(browser,url,out,label,routes,check):
    measurements=[]
    for width in WIDTHS:
        ctx=browser.new_context(viewport={"width":width,"height":900},device_scale_factor=1)
        page=ctx.new_page()
        errors=[]
        page.on("pageerror",lambda error:errors.append(str(error)))
        for name,path in routes.items():
            start=time.perf_counter()
            response=page.goto(url+path,wait_until="load",timeout=30000)
            assert response and response.status==200,(label,name,width)
            page.locator("h1").wait_for()
            dims=page.evaluate("""() => ({viewport:innerWidth,document:document.documentElement.scrollWidth,tableRegions:[...document.querySelectorAll('.table-wrap')].map(x=>({client:x.clientWidth,scroll:x.scrollWidth}))})""")
            page.screenshot(path=str(out/f"{label}-{width}-{name}.png"),full_page=True,animations="disabled")
            measurements.append({"build":label,"width":width,"screen":name,"milliseconds":round((time.perf_counter()-start)*1000,1),"dimensions":dims})
            if check:
                assert dims["document"]<=width+1,(label,name,width,dims)
                assert page.locator("main").count()==page.locator("h1").count()==1
                assert not errors,errors
        if check:
            page.goto(url+"/")
            page.keyboard.press("Tab")
            assert page.evaluate("document.activeElement.classList.contains('skip-link')"),width
            page.locator("#global-q").fill("000001")
            page.locator(".global-search button").click()
            page.locator(".filters select[name=mode]").select_option("identifier")
            page.locator(".filters button").click()
            assert "mode=identifier" in page.url
            page.get_by_role("link",name="Synthetic hospital 000001",exact=True).click()
            assert urlsplit(page.url).path=="/facility"
            page.go_back()
            assert "mode=identifier" in page.url and page.get_by_role("heading",name="Unified search").is_visible()
            page.go_forward()
            assert urlsplit(page.url).path=="/facility"
            page.goto(url+"/facilities?state=AL&sort=name_desc&limit=25")
            assert page.locator(".filters select[name=state]").input_value()=="AL"
            assert page.locator(".filters select[name=sort]").input_value()=="name_desc"
            page.get_by_role("link",name="Next",exact=True).click()
            assert "page=2" in page.url and "state=AL" in page.url and "sort=name_desc" in page.url
            page.goto(url+"/hospital-surveys?row_kind=memo")
            assert page.locator("tbody tr").count()>0
            assert all("memo" in x for x in page.locator("tbody tr").all_inner_texts())
            page.goto(url+"/ownership-coverage?kind=organization_roles")
            assert "row-level organizational projections are not published" in page.locator("main").inner_text()
            page.goto(url+"/certification?registry=qies&row=1")
            assert "2024-01-01" in page.locator("main").inner_text()
            assert page.goto(url+"/certification?registry=qies&row=99999999").status==404
        ctx.close()
    return measurements

def benchmark(url):
    results=[]
    for path,target in TARGETS.items():
        hit(url,path)
        timings=[hit(url,path)[0] for _ in range(5)]
        results.append({"path":path,"median_ms":round(statistics.median(timings),2),"max_ms":max(timings),"target_max_ms":target,"target_met":max(timings)<=target})
    path="/api/search?q=000001&mode=identifier"
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        batch=list(pool.map(lambda _:hit(url,path),range(8)))
    assert all([g["result"]["total"] for g in result["groups"]]==[1,1] for _,result in batch)
    worst=max(ms for ms,_ in batch)
    results.append({"path":path,"concurrent_workers":4,"requests":8,"max_ms":worst,"target_max_ms":2000,"target_met":worst<=2000})
    return results

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("baseline","db","output"):p.add_argument("--"+k,type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    candidate=Path(__file__).resolve().parents[1]
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True,args=["--no-sandbox"])
        with server(a.baseline.resolve(),a.db.resolve(),8083) as url:
            baseline=capture(b,url,a.output,"baseline",BASE,False)
        with server(candidate,a.db.resolve(),8084) as url:
            current=capture(b,url,a.output,"candidate",{**BASE,**EXTRA},True)
            timings=benchmark(url)
        b.close()
    report={"synthetic_fixture_only":True,"screens":baseline+current,"performance":timings,"limitations":["Volume-matched synthetic fixture, not real national data.","Automated checks are not human screenshot review or full WCAG qualification.","Local runner timings, not production latency."]}
    (a.output/"browser-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("BROWSER_QA",json.dumps({"baseline_screens":len(baseline),"candidate_screens":len(current),"performance":timings,"synthetic_fixture_only":True}),flush=True)
    assert all(x["target_met"] for x in timings),"Local target missed; inspect report"
if __name__=="__main__":main()
