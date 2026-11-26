"""Aggregate-only targeted Care Compare infrastructure qualification."""
import argparse, json, re, tempfile
from collections import Counter
from pathlib import Path
from restore_snapshot import LOCK, load_lock, materialize, verify_raw
from remaining_raw_field_profile import csv_rows, HEADERS

FIELDS={
 "dialysis": ("Chain Owned","Late Shift","Offers in-center hemodialysis","Offers peritoneal dialysis","Offers home hemodialysis training"),
 "nursing": ("Automatic Sprinkler Systems in All Required Areas","Most Recent Health Inspection More Than 2 Years Ago","Provider Changed Ownership in Last 12 Months","Special Focus Status"),
 "long-term-hospital": ("Total Number of Beds",),
}
def require(ok,msg):
    if not ok: raise ValueError(msg)
def token(v):
    v=v.strip()
    if not v: return "<blank>"
    require(len(v)<=40 and re.fullmatch(r"[A-Za-z0-9 /.,()_-]+",v),"unexpected categorical token")
    return v
def quantity(v):
    v=v.strip()
    return ("zero" if int(v)==0 else "positive") if re.fullmatch(r"[0-9]{1,9}",v) else "nonnumeric"
def audit(key,header,rows):
    fields=FIELDS[key]
    ix={f:header.index(f) for f in fields}
    counts={f:Counter() for f in fields}
    cross={f:Counter() for f in fields if f.startswith("Offers ")}
    total=0
    for row in rows:
        require(len(row)==len(header),"row width drift")
        total+=1
        for f,i in ix.items():
            v=row[i]
            if key=="long-term-hospital" and quantity(v)!="nonnumeric": v=quantity(v)
            counts[f][token(v)]+=1
        if key=="dialysis":
            q=quantity(row[header.index("# of Dialysis Stations")])
            for f,c in cross.items():
                c[q+" | "+token(row[ix[f]])]+=1
    for c in list(counts.values())+list(cross.values()):
        require(sum(c.values())==total,"count reconciliation")
        require(len(c)<=24,"unexpected domain cardinality")
    return {"rows":total,"literal_counts":counts,"station_service_cross_tabs":cross}
def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path);a=p.parse_args()
    pins={x["key"]:x for x in load_lock(LOCK)["sources"]}
    headers={x["source"]:x for x in json.loads(HEADERS.read_text())["sources"]}
    out={}
    for key in FIELDS:
        pin=pins[key]; h=headers[key]
        require(h["source_sha256"]==pin["sha256"] and h["input_rows"]==pin["input_rows"],"header provenance drift")
        with tempfile.TemporaryDirectory() as d:
            path=materialize(pin,a.raw_dir,Path(d),a.download)
            rows=csv_rows(path,pin)
            try:
                header=next(rows);require(header==[f["field"] for f in h["fields"]],"header drift")
                result=audit(key,header,rows)
            finally: rows.close()
            verify_raw(path,pin)
        require(result["rows"]==pin["input_rows"],"row count drift")
        out[key]={"sha256":pin["sha256"],"release":pin["release"],**result}
    with a.output.open("x") as f: json.dump(out,f,indent=2,sort_keys=True)
    print("INFRASTRUCTURE_AGGREGATES",json.dumps(out,sort_keys=True))
if __name__=="__main__":main()
