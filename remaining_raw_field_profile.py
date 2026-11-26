"""Aggregate profiles of the remaining sixteen pinned national source files.

This is read-only qualification, not ingestion or data publication. Individual
PECOS owner rows are excluded before any field profiling. QCOR narrative and
contact/personal fields receive presence-only counts, never content inspection
or distinct-value retention. Existing national snapshots are not rebuilt.
"""
import argparse
import csv
from collections import Counter
from datetime import datetime,date
from decimal import Decimal
import json
from pathlib import Path
import re
import tempfile
import openpyxl

from collect_registry import source_encoding, open_csv
from collect_qcor_hospital import HEADER
from restore_snapshot import verify_raw, materialize
from pos_raw_field_profile import FieldProfile, read, need, LOCK

ROOT = Path(__file__).resolve().parent
HEADERS = ROOT / "research/care_compare_pecos_exact_headers_20261126.json"
GROUPS = {
    "directory": ("dialysis","home-health","hospice","hospital","long-term-hospital","nursing","rehabilitation"),
    "citations": ("nursing-fire","nursing-health"),
    "pecos": ("hospital-enrollment","hospital-owner","hospital-chow","snf-enrollment","snf-owner","snf-chow"),
    "qcor": ("qcor-hospital",)
}
# Header-level candidate quantities. Meaning and permitted use still require
# publisher review. Never sum unlike measures or infer occupancy/equipment.
COUNT_FIELDS = {
    ("long-term-hospital","Total Number of Beds"): "reported total beds",
    ("nursing","Number of Certified Beds"): "reported certified beds",
    ("dialysis","# of Dialysis Stations"): "reported dialysis stations",
}
YES_NO_FIELDS = {
    ("hospital","Emergency Services"),
    ("dialysis","Offers in-center hemodialysis"),
    ("dialysis","Offers peritoneal dialysis"),
    ("dialysis","Offers home hemodialysis training"),
    *[("home-health",f"Offers {name} Services") for name in
      ("Nursing Care","Physical Therapy","Occupational Therapy","Speech Pathology","Medical Social","Home Health Aide")],
}
MARKERS = {"n/a","na","not reported","not applicable","not available","unknown","suppressed","not applicable/not available"}
def limited(source, field):
    f=field.casefold()
    if source=="qcor-hospital" and f.startswith("statement of deficiency text"):
        return "narrative_excluded_presence_only"
    if any(x in f for x in ("telephone","phone","fax","first name","middle name","last name","title - owner")):
        return "contact_or_personal_presence_only"
    if source.endswith("-owner") and (f.endswith(" - owner") and any(x in f for x in
           ("address","city","state","zip","other type text"))):
        return "owner_address_or_free_text_presence_only"
    return None

class AuditField:
    def __init__(self,source,field):
        self.source=source
        self.field=field
        self.limit=limited(source,field)
        self.base=None if self.limit else FieldProfile()
        self.presence=Counter()
        self.types=Counter()
        self.markers=Counter()
        self.values=Counter()
        self.numeric=None
    def add(self,raw):
        if raw is None:
            s=""
            kind="null"
        elif isinstance(raw,(datetime,date)):
            s=raw.isoformat()
            kind=type(raw).__name__
        elif isinstance(raw,(str,int,float,bool)):
            s=str(raw)
            kind=type(raw).__name__
        else:
            raise ValueError("unexpected structured cell type")
        self.types[kind]+=1
        if self.limit:
            self.presence["nonblank" if s.strip() else "blank"]+=1
            return
        self.base.add(s)
        v=s.strip()
        if v.casefold() in MARKERS:
            self.markers[v.casefold()]+=1
        key=(self.source,self.field)
        if key in COUNT_FIELDS:
            if not v:
                self.values["blank"]+=1
            elif v.casefold() in MARKERS:
                self.values["literal_marker"]+=1
            elif len(v)<=15 and re.fullmatch(r"[0-9]+",v):
                n=int(v)
                self.values["nonnegative_integer"]+=1
                self.values["explicit_zero"]+=int(n==0)
                self.numeric=(n,n,n) if self.numeric is None else (
                    min(n,self.numeric[0]),max(n,self.numeric[1]),self.numeric[2]+n)
            else:
                self.values["other_token"]+=1
        if key in YES_NO_FIELDS:
            if v.casefold() in {"yes","no"}:
                self.values[v.casefold()]+=1
            elif not v:
                self.values["blank"]+=1
            elif v.casefold() in MARKERS:
                self.values["literal_marker"]+=1
            else:
                self.values["other_token"]+=1

    def result(self,total):
        need(sum(self.types.values())==total,"cell type count mismatch")
        if self.limit:
            need(sum(self.presence.values())==total,"restricted presence count mismatch")
            return {"field":self.field,"profile_status":self.limit,"presence":dict(self.presence)}
        r=self.base.result(total)
        r.update(field=self.field,profile_status="aggregate_lexical_profile",
                 cell_types=dict(self.types),literal_marker_counts=dict(self.markers))
        if (self.source,self.field) in COUNT_FIELDS:
            need(sum(v for k,v in self.values.items() if k!="explicit_zero")==total,"quantity reconciliation")
            r["header_quantity_candidate"]={"unit":COUNT_FIELDS[(self.source,self.field)],
              "counts":dict(self.values),
              "range_and_sum":None if self.numeric is None else dict(zip(("min","max","sum"),self.numeric)),
              "status":"header-defined candidate; not new application approval"}
        elif (self.source,self.field) in YES_NO_FIELDS:
            need(sum(self.values.values())==total,"indicator reconciliation")
            r["literal_yes_no_counts"]=dict(self.values)
        return r

def csv_rows(path,item):
    key=item["key"]
    zipped=item.get("metadata",{}).get("zipped",False)
    encoding="utf-8-sig" if item["family"]=="care-compare" else source_encoding(path,zipped)
    with open_csv(path,zipped,encoding) as f:
        reader=csv.reader(f)
        yield next(reader,[])
        for row in reader:
            yield row

def xlsx_rows(path):
    wb=openpyxl.load_workbook(path,read_only=True,data_only=True,keep_links=False)
    try:
        need(wb.sheetnames==["Hospital 2567s"],"QCOR sheet drift")
        ws=wb[wb.sheetnames[0]]
        ws.reset_dimensions()
        rows=ws.iter_rows(values_only=True)
        yield list(next(rows,()))
        for row in rows:
            need(len(row)<=len(HEADER),"unexpected QCOR row width")
            yield list(row)+[None]*(len(HEADER)-len(row))
    finally:
        wb.close()

def profile(item,path,header):
    verify_raw(path,item)
    key=item["key"]
    need(header and len(set(header))==len(header),"invalid expected header")
    rows=xlsx_rows(path) if key=="qcor-hospital" else csv_rows(path,item)
    stats=[AuditField(key,f) for f in header]
    n=excluded=stored=0
    try:
        need(next(rows)==header,"raw source header mismatch")
        owner_ix=header.index("TYPE - OWNER") if key.endswith("-owner") else None
        for row in rows:
            n+=1
            need(len(row)==len(header),"raw source row width mismatch")
            if owner_ix is not None:
                typ=row[owner_ix].strip()
                if typ=="I":
                    excluded+=1
                    continue
                need(typ=="O","unknown PECOS owner type")
            stored+=1
            for field,value in zip(stats,row):
                field.add(value)
    finally:
        rows.close()
    need(n==item["input_rows"] and stored==item["stored_rows"] and excluded==item["excluded_rows"],
         "source input/profiled/excluded count mismatch")
    need(n==stored+excluded,"source reconciliation")
    verify_raw(path,item)
    result=[{"ordinal":i+1,**f.result(stored)} for i,f in enumerate(stats)]
    return {"source":key,"family":item["family"],"period":item["release"],"source_sha256":item["sha256"],
            "source_bytes":item["bytes"],"input_rows":n,"profiled_rows":stored,"excluded_rows":excluded,
            "columns":len(header),"fields":result,
            "scope":"Aggregate-only exact pinned source; lexical profile, not publisher semantic qualification."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--group",choices=sorted(GROUPS),required=True)
    p.add_argument("--raw-dir",type=Path)
    p.add_argument("--download",action="store_true")
    p.add_argument("--output-dir",type=Path,required=True)
    a=p.parse_args()
    need(not a.output_dir.exists(),"new output required")
    a.output_dir.mkdir(parents=True)
    pins={s["key"]:s for s in read(LOCK)["sources"]}
    headers={s["source"]:s for s in read(HEADERS)["sources"]}
    for key in GROUPS[a.group]:
        pin=pins[key]
        if key=="qcor-hospital":
            header=list(HEADER)
        else:
            h=headers[key]
            need(h["source_sha256"]==pin["sha256"] and h["input_rows"]==pin["input_rows"],"header evidence mismatch")
            header=[f["field"] for f in h["fields"]]
        with tempfile.TemporaryDirectory(prefix="remaining-source-profile-") as d:
            path=materialize(pin,a.raw_dir,Path(d),a.download)
            result=profile(pin,path,header)
        with (a.output_dir/(key+".json")).open("x",encoding="utf-8") as f:
            json.dump(result,f,indent=2,sort_keys=True); f.write("\n")
        print("REMAINING_PROFILE_SUMMARY",json.dumps({k:v for k,v in result.items() if k!="fields"},sort_keys=True),flush=True)
        for field in result["fields"]:
            print("REMAINING_PROFILE_FIELD",key,json.dumps(field,separators=(",",":"),sort_keys=True),flush=True)

if __name__=="__main__":
    main()
