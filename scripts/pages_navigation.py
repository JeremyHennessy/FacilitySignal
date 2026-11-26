"""Use the actual task-oriented desktop navigation or mobile workspace selector."""
def open_workspace(page,view):
    target="#"+view
    mobile=page.locator("#mobile-route")
    if mobile.is_visible():
        mobile.select_option(target)
    else:
        link=page.locator("nav[aria-label='Primary navigation'] a[href='"+target+"']")
        group=link.locator("xpath=ancestor::details[1]")
        if group.count() and not group.evaluate("(e)=>e.open"):
            group.locator("summary").click()
        link.click()
