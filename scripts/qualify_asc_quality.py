"""FS-041 national ASC Quality Reporting release screening.

Source-native facility/year observations; no individual patient records,
facility risk ranking, clinical rates published, or canonical identity merges.
Aggregate-only audit with exact release, bytes, column and row reconciliation.
"""
import argparse
import csv
import hashlib
import json
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import collect_cms as cms
from build_combined import require, sha
from local_research import STATES

DATASET = "4jcv-atw7"
RELEASE = "2026-11-12"
MODIFIED = "2026-10-27"
EXPECTED = 5786
MAX_BYTES = 16 * 1024 * 1024
HEADER = ["Facility Name", "Facility ID", "NPI", "City/Town", "State", "ZIP Code", "Year"]

def rate(n):
    return [f"ASC-{n} Rate*", f"ASC-{n} Footnote"]

def visits(n, measure="Rate"):
    return [f"ASC-{n} Total Cases", f"ASC-{n} Performance Category",
            f"ASC-{n} RSHV {measure}", f"ASC-{n} Interval Lower Limit",
            f"ASC-{n} Interval Upper Limit", f"ASC-{n} Footnote"]

for n in (1,2,3,4,9,11):
    HEADER += rate(n)
HEADER += visits(12) + rate(13) + rate(14) + visits(17) + visits(18) + visits(19,"Ratio")

MISSING = {"not available", "not applicable", "n/a", "na", "null", "--", "-", "none"}

def state_of(raw):
    value = raw.strip()
    return "blank" if not value else "publisher_missing_literal" if value.casefold() in MISSING else "populated"

def screen(stream, expected):
    require(type(expected) is int and 0 < expected <= 10000, "row bound")
    reader = csv.reader(stream, strict=True)
    require(next(reader, None) == HEADER, "FS041 exact header drift")
    profiles = [Counter() for _ in HEADER]
    states, ids, npis, years = (Counter() for _ in range(4))
    keys, facility_ids, npi_ids = set(), set(), set()
    repeated, missing_key, n = 0, 0, 0
    for n, row in enumerate(reader, 1):
        require(n <= expected and len(row) == len(HEADER), "row width/count drift")
        for value, profile in zip(row, profiles):
            profile[state_of(value)] += 1
        _, ident, npi, _, state, _, year = (v.strip() for v in row[:7])
        states[state if state in STATES else "unknown_or_other"] += 1
        ids["ten_alphanumeric" if re.fullmatch(r"[A-Z0-9]{10}", ident) else "blank" if not ident else "other_shape"] += 1
        npis["ten_digits" if re.fullmatch(r"[0-9]{10}", npi) else "blank" if not npi else "other_shape"] += 1
        years[year if re.fullmatch(r"20[0-9]{2}",year) else "unknown_or_other"] += 1
        if state_of(ident) == "populated":
            facility_ids.add(ident)
        if re.fullmatch(r"[0-9]{10}", npi):
            npi_ids.add(npi)
        if state_of(ident) != "populated" or not re.fullmatch(r"20[0-9]{2}",year):
            missing_key += 1
        else:
            key = (ident, year)
            if key in keys:
                repeated += 1
            keys.add(key)
    require(n == expected == len(keys)+repeated+missing_key, "source row reconciliation")
    require(all(sum(p.values()) == n for p in profiles)
            and all(sum(c.values()) == n for c in (states,ids,npis,years)), "profile reconciliation")
    return {"source_id":"FS-041", "dataset_id":DATASET, "input_rows":n,
            "source_columns":len(HEADER),"field_presence_profiles":dict(zip(HEADER,map(dict,profiles))),
            "distinct_source_facility_ids":len(facility_ids),"distinct_ten_digit_npi_tokens":len(npi_ids),
            "distinct_facility_year_keys":len(keys),"repeated_facility_year_rows":repeated,
            "missing_or_unreviewed_facility_year_rows":missing_key,
            "facility_id_shapes":dict(ids),"npi_shapes":dict(npis),"report_years":dict(years),
            "jurisdictions_represented":len(set(states)&STATES),"jurisdiction_row_counts":dict(states),
            "row_level_retained":0,"azure_writes":0,"canonical_matches":0,
            "reuse_review":"pending","public_promotion":False,
            "scope":"Aggregate structural screening only. Facility/year key is provisional, NPI shape is not identity verification, reporting participation is not current certification. No clinical values or facility identifiers published; missing/suppressed footnotes require dictionary qualification."}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--audit",type=Path,required=True)
    args=parser.parse_args()
    require(not args.audit.exists(),"audit already exists")
    meta=cms.metadata(DATASET)
    count=cms.count(DATASET)
    require(meta["released"]==RELEASE and meta["modified"]==MODIFIED and count==EXPECTED,
            "publisher release or count changed; review before download")
    with tempfile.TemporaryDirectory(prefix="fs041-private-") as directory:
        path=Path(directory)/"source.csv"
        digest=hashlib.sha256()
        size=0
        with cms.response(meta["url"]) as response, path.open("xb") as out:
            cms.allowed(response.geturl())
            while chunk:=response.read(1024*1024):
                size+=len(chunk)
                require(size<=MAX_BYTES,"source byte bound")
                digest.update(chunk)
                out.write(chunk)
        require(size>0 and sha(path)==digest.hexdigest(),"source integrity")
        require(cms.metadata(DATASET)==meta and cms.count(DATASET)==count,"publisher drift")
        with path.open(encoding="utf-8-sig",newline="") as stream:
            result=screen(stream,count)
        require(sha(path)==digest.hexdigest(),"local source mutation")
    result.update(publisher={**meta,"sha256":digest.hexdigest(),"bytes":size},
                  retrieved_at=datetime.now(timezone.utc).isoformat(),
                  publisher_documentation="https://data.cms.gov/provider-data/topics/hospitals/ambulatory-surgical-centers/")
    with args.audit.open("x",encoding="utf-8") as out:
        json.dump(result,out,indent=2,sort_keys=True)
        out.write("\n")
    print("FS041_AGGREGATE_AUDIT",json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    try:
        main()
    except Exception as error:
        print("FS041_QUALIFICATION_FAILED",type(error).__name__,flush=True)
        raise SystemExit(1) from None
