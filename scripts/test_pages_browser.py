import json, os, subprocess, time
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
port=8091
url=f"http://127.0.0.1:{port}/"
server=subprocess.Popen(["python","-m","http.server",str(port),"--bind","127.0.0.1"],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,args=["--no-sandbox"])
        for width in (390,768,1024,1440):
            page=b.new_page(viewport={"width":width,"height":900})
            page.goto(url)
            page.get_by_role("heading",name="National overview").wait_for()
            page.get_by_text("48,004",exact=True).wait_for()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
            page.get_by_role("link",name="Source register",exact=True).click()
            page.get_by_text("176 source entries",exact=False).wait_for()
            page.get_by_role("link",name="Ownership coverage",exact=True).click()
            page.get_by_role("heading",name="Ownership evidence coverage").wait_for()
            page.close()
        page=b.new_page()
        page.goto(url+"#facilities?source=hospital")
        page.locator(".table-wrap, .error").first.wait_for(timeout=90000)
        assert page.locator(".table-wrap").count(),page.locator(".error").all_inner_texts()
        rows=page.locator("tbody tr")
        assert 0<rows.count()<=25
        record=rows.first.locator("a").first
        record.click()
        page.get_by_role("heading",name="Source record").wait_for()
        page.locator(".detail-grid, .error").first.wait_for(timeout=90000)
        assert page.locator(".detail-grid").count(),page.locator(".error").all_inner_texts()
        page.go_back()
        page.locator(".table-wrap").first.wait_for(timeout=90000)
        page.locator("select[name=state]").select_option("NY")
        page.locator(".toolbar button").click()
        page.locator(".table-wrap,.error,.empty").first.wait_for(timeout=90000)
        assert page.locator(".table-wrap").count(),page.locator(".error").all_inner_texts()
        for row in page.locator("tbody tr").all():
            assert "NY" in row.locator("td").nth(1).inner_text()
        print("LIVE_CMS_PAGES_BROWSER_PASS",flush=True)
        b.close()
finally:
    server.terminate()
    server.wait(timeout=5)
