"""Aggregate-only date-order audit of the exact pinned iQIES release; no parsing change."""
import argparse
import csv
import json
import re
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import collect_registry as registry
from build_combined import require
from restore_snapshot import LOCK,load_lock,materialize,verify_raw
from probe_pos_fields import INVENTORY

def calendar_bucket(raw):
    s=raw.strip()
    if s.casefold()=="not available":return "not_available"
    if not s:return "blank"
    m=re.fullmatch(r"([0-9]{1,2})/([0-9]{1,2})/([0-9]{4})",s)
    if not m:return "other_shape"
    a,b,y=map(int,m.groups())
    def valid(month,day):
        try:return date(y,month,day)
        except ValueError:return None
    mdy,dmy=valid(a,b),valid(b,a)
    if mdy and dmy:return "both_same" if mdy==dmy else "both_different"
    if mdy:return "mdy_only"
    if dmy:return "dmy_only"
    return "neither_valid"

def audit(source,item):
    verify_raw(source,item)
    headers=[x["field"] for x in json.loads(INVENTORY.read_text())["registries"]["iqies"]["fields"]]
    counts=Counter();n=0
    with registry.open_csv(source,item["metadata"]["zipped"],registry.source_encoding(source,item["metadata"]["zipped"])) as f:
        reader=csv.DictReader(f)
        require(reader.fieldnames==headers and "trmntn_exprtn_dt" in headers,"pinned schema mismatch")
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()),"malformed source row")
            counts[calendar_bucket(row["trmntn_exprtn_dt"])]+=1;n+=1
    require(n==item["input_rows"]==100334 and sum(counts.values())==n,"row reconciliation")
    slash=sum(counts[k] for k in ("mdy_only","dmy_only","both_same","both_different","neither_valid"))
    require(slash==25568 and counts["not_available"]==74766,"prior date-shape audit mismatch")
    verify_raw(source,item)
    return {"source_sha256":item["sha256"],"source_period":item["release"],"source_rows":n,"calendar_bucket_counts":dict(counts),"slash_rows":slash,
            "interpretation":"Calendar validity alone is evidence of format consistency, not proof of each ambiguous date. No dates, identifiers or row-level records retained; no parser or production change."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit",type=Path,required=True);p.add_argument("--raw-dir",type=Path);p.add_argument("--download",action="store_true");a=p.parse_args()
    require(not a.audit.exists(),"audit already exists")
    item=next(s for s in load_lock(LOCK)["sources"] if s["family"]=="registry" and s["key"]=="iqies")
    with tempfile.TemporaryDirectory(prefix="iqies-date-order-") as t:
        source=materialize(item,a.raw_dir,Path(t),a.download)
        result=audit(source,item)
    a.audit.parent.mkdir(parents=True,exist_ok=True);a.audit.write_text(json.dumps(result,indent=2)+"\n")
    print("IQIES_DATE_ORDER_AUDIT",json.dumps(result),flush=True)

if __name__=="__main__":main()
