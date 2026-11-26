"""Independent live public capacity verification against existing checked-in shards."""
import json
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
URL="https://jeremyhennessy.github.io/FacilitySignal/"
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"live-capacity"
OUT.mkdir(exist_ok=True)
def expected(key,state=None):
    rows=json.loads((ROOT/f"web/public-directory/{key}.json").read_text())["records"]
    if state:rows=[r for r in rows if r["state"]==state]
    known=[]
    for r in rows:
        s=str(r.get("capacity") or "").strip()
        if re.fullmatch(r"[0-9]+",s) and int(s)<=9007199254740991:known.append(int(s))
    return [f"{len(rows):,}",f"{sum(known):,}" if known else "—",f"{len(known):,}",f"{len(rows)-len(known):,}"]

with sync_playwright() as p:
    b=p.chromium.launch(headless=True,args=["--no-sandbox"])
    for width in (390,1440):
        page=b.new_page(viewport={"width":width,"height":900})
        errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        res=page.goto(URL,wait_until="load",timeout=30000)
        assert res and res.status==200
        page.get_by_role("link",name="Capacity explorer",exact=True).click()
        for key,state in (("nursing",None),("dialysis","NY")):
            if state:page.goto(URL+"#capacity?source="+key+"&state="+state)
            page.get_by_role("columnheader",name="Certified beds" if key=="nursing" else "Dialysis stations",exact=True).wait_for()
            vals=page.locator("#app .metrics .metric strong").all_inner_texts()
            assert vals==expected(key,state),(key,vals,expected(key,state))
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
            assert not errors,errors
            # Do not retain row-level screenshots or browser contents.
        page.close()
    b.close()
report={"url":URL,"viewport_widths":[390,1440],"checks":["HTTP 200","navigation","nursing totals","NY dialysis totals","no page errors","no viewport overflow"],"scope":"existing public static projection only"}
(OUT/"report.json").write_text(json.dumps(report,indent=2)+"\n")
print("LIVE_CAPACITY_PASS",json.dumps(report),flush=True)
