"""Verify hospital aggregate scope, interactive filters, directory navigation and responsive rendering."""
import json, os, subprocess, time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
URL="http://127.0.0.1:8099/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"hospital-infrastructure-evidence"
OUT.mkdir(exist_ok=True)
G={g["id"]:g for s in json.loads((ROOT/"web/public-intelligence.json").read_text())["sections"] for g in s["groups"]}
IDS=["qies-hospital-comparison","qies-hospital-service-subset","qies-hospital-count-subset","hospital-enrollment-subgroups"]
server=subprocess.Popen(["python","-m","http.server","8099","--bind","127.0.0.1"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
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
            page.goto(URL+"#hospital-infrastructure")
            page.get_by_role("heading",name="Hospital enrollment subgroup classifications").wait_for()
            tables=page.locator("#app .intelligence-table")
            assert tables.count()==4
            for i,id in enumerate(IDS):
                assert [r.locator("td").all_inner_texts() for r in tables.nth(i).locator("tbody tr").all()]==[[f"{x:,}" if type(x) is int else x for x in row] for row in G[id]["rows"]]
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            page.screenshot(path=str(OUT/f"{width}-hospital-infrastructure.png"),full_page=True)
            for i,label,q in ((1,"Filter service names","dialysis"),(2,"Filter infrastructure field names","ambulance")):
                field=page.get_by_label(label);field.fill(q)
                expected=sum(q in r[0].lower() for r in G[IDS[i]]["rows"])
                assert tables.nth(i).locator("tbody tr:visible").count()==expected
                field.fill("zzzz-no-matches");assert tables.nth(i).locator("tbody tr:visible").count()==0
                field.fill("");assert tables.nth(i).locator("tbody tr:visible").count()==len(G[IDS[i]]["rows"])
            page.locator("select[name=state]").select_option("NY")
            page.get_by_role("button",name="Browse hospital records").click()
            assert page.url.endswith("#facilities?source=hospital&state=NY")
            page.go_back();page.get_by_role("heading",name="Hospital enrollment subgroup classifications").wait_for()
            assert not errors,errors
            page.close()
        b.close()
    print("HOSPITAL_INFRASTRUCTURE_BROWSER_PASS",flush=True)
finally:
    server.terminate();server.wait(timeout=5)
