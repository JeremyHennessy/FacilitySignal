"""Aggregate-only medical service-area classification of the pinned ECHO release.

This is not a PWS qualification waiver, healthcare property match, compliance
assessment, or data publication. Only national aggregate counts are emitted.
"""
import argparse
import csv
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import zipfile
from collections import Counter
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.qualify_epa_sdwa import download,require,key_format,MEMBER,MAX_EXPANDED

PIN="cad153417ac7f22726bd4b5ebe1cb4aca6088b45910a0b343324fc82cf78ce21"
DOC="https://echo.epa.gov/help/facility-search/drinking-water-search-results-help"
FIELDS={"PWSID","SERVICE_AREA_TYPE_CODE","SERVICE_AREA_TYPE_DESC","PWS_ACTIVITY_CODE"}
VALID_FORMATS={"standard","utah","epa_region"}

def area(code,description):
    c,d=code.strip(),description.strip().casefold()
    if c=="MF" and d=="medical facility":return "exact_code_and_description"
    if c=="MF":return "medical_code_description_unconfirmed"
    if d=="medical facility":return "medical_description_code_unconfirmed"
    if not c:return "missing_code"
    return "other_code"

def audit(path,encoding="utf-8-sig"):
    counts=Counter();cross=Counter();activity=Counter();n=0
    with closing(sqlite3.connect(":memory:")) as db,zipfile.ZipFile(path) as z:
        members=z.infolist()
        require(len(members)==1 and members[0].filename==MEMBER,"archive membership")
        require(0<members[0].file_size<=MAX_EXPANDED and not members[0].flag_bits&1,"archive limit")
        db.execute("CREATE TABLE keys(source_id TEXT PRIMARY KEY)")
        with z.open(members[0]) as raw,io.TextIOWrapper(raw,encoding=encoding,newline="") as stream:
            reader=csv.DictReader(stream,strict=True);h=reader.fieldnames or []
            require(len(h)==len(set(h)) and FIELDS<=set(h),"schema")
            for row in reader:
                require(None not in row and all(v is not None for v in row.values()),"malformed row")
                n+=1
                key=row["PWSID"];require(key and key==key.strip(),"missing or whitespace key")
                require(db.execute("INSERT OR IGNORE INTO keys VALUES(?)",(key,)).rowcount==1,"duplicate source key")
                fmt="documented_format" if key_format(key) in VALID_FORMATS else "unresolved_format"
                bucket=area(row["SERVICE_AREA_TYPE_CODE"],row["SERVICE_AREA_TYPE_DESC"])
                counts[bucket]+=1;cross[(fmt,bucket)]+=1
                if bucket=="exact_code_and_description":
                    token=row["PWS_ACTIVITY_CODE"].strip()
                    activity[token if token in ("A","I","N","M","P") else "other_or_missing"]+=1
        require(n>0 and n==sum(counts.values())==sum(cross.values())==db.execute("SELECT count(*) FROM keys").fetchone()[0],"reconciliation")
    require(sum(activity.values())==counts["exact_code_and_description"],"medical activity reconciliation")
    return {"source_rows":n,"area_counts":dict(counts),
            "area_by_identifier_state":{f:{b:v for (fmt,b),v in cross.items() if fmt==f} for f in ("documented_format","unresolved_format")},
            "exact_medical_area_activity_raw_code_counts":dict(activity),
            "qualification":"aggregate_service_area_only",
            "limits":"Source-reported primary service area classification, not a healthcare site, ownership, equipment, compliance, or procurement match. Unresolved identifiers stay unresolved; no individual records retained."}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--audit",type=Path,required=True);p.add_argument("--source",type=Path);p.add_argument("--download",action="store_true");a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    require(bool(a.source)!=a.download,"choose an existing local source or explicit one-time retrieval")
    with tempfile.TemporaryDirectory(prefix="epa-medical-area-") as t:
        path=a.source or Path(t)/"source.zip";meta=download(path) if a.download else {}
        require(path.is_file() and not path.is_symlink(),"source missing")
        with path.open("rb") as f: digest=hashlib.file_digest(f,"sha256").hexdigest()
        require(digest==PIN,"source release changed; stop for new qualification")
        result=audit(path)
        require(result["source_rows"]==434757,"prior row baseline mismatch")
        require(sum(result["area_by_identifier_state"]["documented_format"].values())==431470,"documented format baseline mismatch")
        require(sum(result["area_by_identifier_state"]["unresolved_format"].values())==3287,"unresolved baseline mismatch")
        with path.open("rb") as f:require(hashlib.file_digest(f,"sha256").hexdigest()==digest,"source mutated")
    result.update({"source_sha256":digest,"publisher_definition":DOC,"reuse_review":"pending","retrieval":meta})
    a.audit.parent.mkdir(parents=True,exist_ok=True);a.audit.write_text(json.dumps(result,indent=2)+"\n")
    print("EPA_MEDICAL_AREA_AGGREGATE",json.dumps(result),flush=True)

if __name__=="__main__":main()
