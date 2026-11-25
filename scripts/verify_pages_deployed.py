"""Verify real GitHub Pages baseline, not a local server."""
import json, os, time
from pathlib import Path
from playwright.sync_api import sync_playwright
URL="https://jeremyhennessy.github.io/FacilitySignal/"
out=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"pages-research-evidence"
out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
    page=browser.new_page(viewport={"width":1440,"height":900})
    for attempt in range(6):
        response=page.goto(URL,wait_until="load",timeout=30000)
        try:
            page.get_by_text("48,004",exact=True).wait_for(timeout=10000)
            break
        except Exception:
            if attempt==5:raise
            time.sleep(5)
    assert response.status==200
    page.screenshot(path=str(out/"deployed-overview.png"),full_page=True,animations="disabled")
    page.goto(URL+"#facilities?source=hospital&state=NY")
    page.locator("tbody tr").first.wait_for(timeout=30000)
    assert all("NY" in r.locator("td").nth(1).inner_text() for r in page.locator("tbody tr").all())
    page.locator("tbody tr").first.locator("a").first.click()
    page.locator(".detail-grid").first.wait_for(timeout=30000)
    page.screenshot(path=str(out/"deployed-facility.png"),full_page=True,animations="disabled")
    print("PUBLIC_PAGES_DEPLOYED_VERIFIED",URL,flush=True)
    browser.close()
