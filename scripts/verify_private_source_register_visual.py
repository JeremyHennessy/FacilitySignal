"""Exact source register metadata browser check; local candidate or ordinary public URL."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"private-source-register-visual"
URL="https://jeremyhennessy.github.io/FacilitySignal/"
def run(base):
    OUT.mkdir(exist_ok=True)
    raw=(ROOT/"research/coverage_status.json").read_bytes()
    cov=json.loads(raw);plan=json.loads((ROOT/"research/private_source_register_receipt_map_20261126.json").read_text())
    overlay={x["id"]:x for x in cov["sources"]};seen=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for width in (390,768,1024,1440):
            ctx=browser.new_context(viewport={"width":width,"height":900},device_scale_factor=1)
            page=ctx.new_page();page.goto(base+"#sources",wait_until="networkidle")
            page.get_by_role("heading",name="Source register",exact=True).wait_for()
            data=page.evaluate("async()=>Array.from(new Uint8Array(await (await fetch('research/coverage_status.json')).arrayBuffer()))")
            assert hashlib.sha256(bytes(data)).hexdigest()==hashlib.sha256(raw).hexdigest(),"loaded coverage SHA mismatch"
            for ident,rule in plan["sources"].items():
                page.goto(base+"#sources?"+urlencode({"q":ident}))
                row=page.locator("tbody tr").filter(has_text=ident);row.wait_for()
                assert row.count()==1
                assert row.locator("td").nth(2).inner_text()==rule["display_status"],ident
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1"),ident
                if ident in ("FS-004","FS-049","FS-050","FS-055","FS-070","FS-105","FS-150","FS-157"):
                    page.screenshot(path=str(OUT/f"{width}-{ident}.png"),full_page=True)
                seen.append({"width":width,"source":ident,"status":rule["display_status"]})
            ctx.close()
        browser.close()
    result={"status":"PASS","route_checks":len(seen),"widths":[390,768,1024,1440],"coverage_sha256":hashlib.sha256(raw).hexdigest(),"checks":seen,"scope":"local candidate" if base.startswith("http://127.") else "ordinary public URL","revision":os.environ.get("GITHUB_SHA","local")}
    (OUT/"report.json").write_text(json.dumps(result,indent=2)+"\n")
    print("SOURCE_REGISTER_BROWSER_PASS",json.dumps({k:v for k,v in result.items() if k!="checks"}),flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument("--local",action="store_true");a=p.parse_args()
    if not a.local:run(URL);return
    server=subprocess.Popen(["python","-m","http.server","8098","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with urlopen("http://127.0.0.1:8098/",timeout=2):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError("local HTTP unavailable")
        run("http://127.0.0.1:8098/")
    finally:server.terminate();server.wait(timeout=5)
if __name__=="__main__":main()
