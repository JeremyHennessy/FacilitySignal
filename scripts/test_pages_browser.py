"""Browser qualification of public snapshot, no live CMS dependency."""
import json, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
meta=json.loads((root/"web/public-directory/manifest.json").read_text())
assert meta["provider_rows"]==48004 and meta["citation_source_rows"]==619069 and len(meta["jurisdictions"])==56
server=subprocess.Popen(["python","-m","http.server","8091","--bind","127.0.0.1"],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        for width in (390,768,1024,1440):
            page=b.new_page(viewport={"width":width,"height":900})
            page.goto("http://127.0.0.1:8091/")
            page.get_by_text("48,004",exact=True).wait_for()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
            page.get_by_role("link",name="Source register",exact=True).click()
            page.get_by_text("176 source entries",exact=False).wait_for()
            page.get_by_role("link",name="Facilities",exact=True).click()
            page.locator("tbody tr").first.wait_for()
            assert 0<page.locator("tbody tr").count()<=25
            page.locator("select[name=state]").select_option("NY")
            page.locator(".toolbar button").click()
            page.locator("tbody tr").first.wait_for()
            assert all("NY" in r.locator("td").nth(1).inner_text() for r in page.locator("tbody tr").all())
            page.locator("tbody tr").first.locator("a").first.click()
            page.locator(".detail-grid").first.wait_for()
            page.go_back()
            page.locator("tbody tr").first.wait_for()
            page.get_by_role("link",name="Nursing home citations",exact=True).click()
            page.get_by_role("columnheader",name="Historical citation rows").wait_for()
            assert page.locator("tbody tr").count()>0
            page.get_by_role("link",name="Certifications & laboratories",exact=True).click()
            page.get_by_role("heading",name="Certifications & laboratories").wait_for()
            assert page.get_by_text("row-level registry data are not published",exact=False).count()==1
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
            page.close()
        print("PUBLIC_PAGES_BROWSER_PASS widths=390,768,1024,1440; directory, details, filters, history, citation aggregates, registry coverage")
        b.close()
finally:
    server.terminate()
    server.wait(timeout=5)
