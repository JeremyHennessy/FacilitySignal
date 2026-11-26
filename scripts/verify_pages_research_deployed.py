"""Confirm the currently deployed research release against the public URL."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
URL="https://jeremyhennessy.github.io/FacilitySignal/"
out=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"pages-capacity-evidence"
out.mkdir(exist_ok=True)
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,args=["--no-sandbox"])
    for width in (390,1440):
        page=b.new_page(viewport={"width":width,"height":900})
        response=page.goto(URL,wait_until="load",timeout=30000)
        assert response.status==200
        page.get_by_text("48,004",exact=True).wait_for()
        page.get_by_role("link",name="Market explorer",exact=True).click()
        page.get_by_text("48,004 provider source records across 7 of 7 sources.",exact=False).wait_for()
        assert page.locator("tbody tr").count()==56
        assert "VT" in page.locator("tbody tr td:first-child").all_inner_texts()
        assert sum(int(s.replace(",","")) for s in page.locator("tbody tr td:last-child").all_inner_texts())==48004
        page.screenshot(path=str(out/f"deployed-{width}-market.png"),full_page=True)
        page.goto(URL+"#facilities?source=hospital&state=NY")
        page.locator("tbody tr").first.wait_for()
        assert all("NY" in x.locator("td").nth(1).inner_text() for x in page.locator("tbody tr").all())
        page.locator("tbody tr").first.locator("a").first.click()
        page.locator(".detail-grid").first.wait_for()
        page.close()
    b.close()
print("DEPLOYED_RESEARCH_BASELINE_PASS",URL,flush=True)
