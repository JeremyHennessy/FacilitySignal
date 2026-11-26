"""Pin public app script/style URLs to the current file content.

Run --write after any change to web/pages.js or web/pages.css, before committing.
The default --check is read-only and fails if the entry point is stale.
"""
import argparse,hashlib,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ASSETS=("web/pages.js","web/pages.css")
def asset_hash(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
def stamped(html):
    for asset in ASSETS:
        pattern=r'"'+re.escape(asset)+r'(?:\?v=[0-9a-f]{16})?"'
        html,n=re.subn(pattern,'"'+asset+"?v="+asset_hash(asset)[:16]+'"',html)
        if n!=1:raise ValueError("Expected one entry-point reference to "+asset)
    return html
def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group()
    g.add_argument("--check",action="store_true")
    g.add_argument("--write",action="store_true")
    a=p.parse_args()
    path=ROOT/"index.html"
    current=path.read_text(encoding="utf-8")
    wanted=stamped(current)
    if a.write:path.write_text(wanted,encoding="utf-8")
    elif current!=wanted:raise SystemExit("Stale asset URLs: run python scripts/stamp_pages_assets.py --write and include index.html in the qualified change")
    print("PAGES_ASSET_STAMP_PASS")
if __name__=="__main__":main()
