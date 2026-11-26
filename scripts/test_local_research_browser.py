"""Verify new local research routes on controlled source-scoped fixtures."""
import os,subprocess,tempfile,time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
from tests.test_local_research import LocalResearchTests
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"local-research-fixture-evidence";OUT.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as t:
    fixture=LocalResearchTests();fixture.setUp();fixture.seed_services()
    # Reuse the already qualified test setup for deterministic ownership data.
    fixture.test_portfolio_preserves_role_grain()
    path=Path(t)/"fixture.sqlite3"
    import sqlite3
    fixture.db.commit()
    with sqlite3.connect(path) as copy:fixture.db.backup(copy)
    fixture.tearDown()
    server=subprocess.Popen(["python","facilitysignal.py","--db",str(path),"serve","--port","8094"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with urlopen("http://127.0.0.1:8094/api/service-research?field=dlys_stn_cnt",timeout=2) as r:
                    import json
                    assert json.load(r)["total"]==2
                    break
            except OSError:time.sleep(.1)
        else:raise RuntimeError("local HTTP unavailable")
        with sync_playwright() as p:
            b=p.chromium.launch(headless=True,args=["--no-sandbox"])
            for width in (390,1440):
                page=b.new_page(viewport={"width":width,"height":900})
                for name,url,expected in [
                    ("service","/service-research?field=dlys_stn_cnt&state=NY","2 matching source observations"),
                    ("portfolio","/organization-research?owner_pac_id=456","1 matching source observations")]:
                    page.goto("http://127.0.0.1:8094"+url)
                    page.get_by_role("heading",name=expected).wait_for()
                    if name=="service":
                        assert page.locator("input[name=registry]").input_value()=="iqies"
                        assert page.locator("select[name=code]").count()==0
                        page.get_by_role("link",name="QIES literal hospital codes").click()
                        page.get_by_role("heading",name="3 matching source observations").wait_for()
                        assert page.locator("input[name=registry]").input_value()=="qies"
                        assert page.locator("input[name=min]").count()==0
                        page.get_by_role("link",name="iQIES capability fields").click()
                        page.get_by_role("heading",name="1 matching source observations").wait_for()
                        page.goto("http://127.0.0.1:8094"+url)
                        page.get_by_role("heading",name=expected).wait_for()
                    page.screenshot(path=str(OUT/f"{width}-{name}.png"),full_page=True)
                page.close()
            b.close()
        print("LOCAL_RESEARCH_FIXTURE_BROWSER_PASS",flush=True)
    finally:server.terminate();server.wait(timeout=5)
