"""FS-042: exact-release provider-to-directory evidence, aggregate only.

Two small pinned public CMS files; no Azure, no raw publication or canonical
property merges. Reuse of source material is documented separately from
application publication clearance. Prefer authorized local exact copies.
"""
import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CCN = "CMS Certification Number (CCN)"
RELEASE = "2026-09-23"
DIRECTORY = [CCN, "Provider Name", "Address Line 1", "Address Line 2", "City/Town",
             "State", "ZIP Code", "County/Parish", "Telephone Number", "CMS Region",
             "Ownership Type", "Certification Date", "Total Number of Beds"]
PROVIDER = DIRECTORY[:10] + ["Measure Code", "Score", "Footnote", "Start Date",
                             "End Date", "Measure Date Range"]
CONTEXT = ("Provider Name", "Address Line 1", "City/Town", "ZIP Code")
MISSING = {"", "-", "--", "not available", "not applicable", "n/a", "null"}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def rows(payload, header, expected):
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline=""), strict=True)
    require(reader.fieldnames == header, "header drift")
    n = 0
    for n, row in enumerate(reader, 1):
        require(n <= expected and None not in row and None not in row.values(), "row width/count drift")
        require(re.fullmatch(r"[0-9]{6}", row[CCN]) is not None, "invalid CCN token")
        yield row
    require(n == expected, "row count drift")

def context(row):
    return tuple(row[k].strip().casefold() for k in CONTEXT)

def classify(directory, provider):
    if directory is None:
        return "unmatched_ccn"
    a, b = directory["State"], provider["State"]
    if not re.fullmatch(r"[A-Z]{2}", a) or not re.fullmatch(r"[A-Z]{2}", b):
        return "state_unresolved"
    if a != b:
        return "state_conflict"
    x, y = context(directory), context(provider)
    if any(t in MISSING for t in x+y):
        return "same_state_context_missing"
    return "same_state_exact_context" if x == y else "same_state_context_differs"

def screen(directory_bytes, provider_bytes, directory_count, provider_count):
    directory = {}
    for row in rows(directory_bytes, DIRECTORY, directory_count):
        require(row[CCN] not in directory, "duplicate directory CCN")
        directory[row[CCN]] = {k:row[k] for k in ("State",)+CONTEXT}
    by_provider, row_counts, keys = {}, Counter(), set()
    for row in rows(provider_bytes, PROVIDER, provider_count):
        key = tuple(row[k] for k in (CCN, "Measure Code", "Start Date", "End Date", "Measure Date Range"))
        require(key not in keys and bool(key[1]), "duplicate or missing provider measure key")
        keys.add(key)
        token = row[CCN]
        state = classify(directory.get(token), row)
        row_counts[state] += 1
        by_provider.setdefault(token, set()).add(state)
    # A CCN with mixed contexts is not a single corroborated provider.
    provider_counts = Counter(next(iter(states)) if len(states)==1 else "mixed_evidence"
                              for states in by_provider.values())
    intersection = set(directory) & set(by_provider)
    require(sum(row_counts.values()) == provider_count and
            sum(provider_counts.values()) == len(by_provider), "aggregate reconciliation")
    return {"directory_rows":directory_count, "provider_observations":provider_count,
            "distinct_provider_ccns":len(by_provider), "exact_ccn_intersection":len(intersection),
            "directory_only_ccns":len(set(directory)-set(by_provider)),
            "provider_only_ccns":len(set(by_provider)-set(directory)),
            "observation_evidence_states":dict(row_counts),
            "provider_evidence_states":dict(provider_counts),
            "canonical_matches":0, "retained_rows":0, "azure_calls":0,
            "public_promotion":False, "score_values_consumed_for_analysis":0,
            "boundary":"Same-release publisher CCN and textual context only; not physical property, legal ownership, current status, or longitudinal attribution."}

def pins():
    baseline = json.loads((ROOT/"research/snapshot_release_20261125.json").read_text())
    directory = next(x for x in baseline["sources"] if x.get("key")=="long-term-hospital")
    quality = json.loads((ROOT/"research/fs042_ltch_quality_qualification_20261127.json").read_text())["audit"]["sources"]["provider"]
    p = quality["publisher"]
    require(directory["catalog_id"]=="azum-44iv" and directory["release"]==p["released"]==RELEASE
            and p["id"]=="fp6g-2gsn" and directory["input_rows"]==311
            and quality["input_rows"]==24258 and directory["bytes"]==43350
            and p["bytes"]==4049344, "source pin drift")
    return {"directory":{"id":directory["catalog_id"],"modified":"2026-08-12","rows":directory["input_rows"],
                         "bytes":directory["bytes"],"sha256":directory["sha256"],"url":directory["download_url"]},
            "provider":{"id":p["id"],"modified":p["modified"],"rows":quality["input_rows"],
                        "bytes":p["bytes"],"sha256":p["sha256"],"url":p["url"]}}

def verify_bytes(payload, pin):
    require(len(payload)==pin["bytes"] and hashlib.sha256(payload).hexdigest()==pin["sha256"],
            "pinned source bytes differ")
    return payload

def read_local(path, pin):
    with path.open("rb") as src:
        return verify_bytes(src.read(pin["bytes"]+1), pin)

def retrieve(pin):
    # Only called in the explicit bounded publisher qualification mode.
    from scripts import collect_cms as cms
    meta = cms.metadata(pin["id"])
    require(meta["url"]==pin["url"] and meta["released"]==RELEASE
            and meta["modified"]==pin["modified"] and cms.count(pin["id"])==pin["rows"],
            "publisher release drift")
    with cms.response(pin["url"]) as response:
        cms.allowed(response.geturl())
        payload = verify_bytes(response.read(pin["bytes"]+1), pin)
    require(cms.metadata(pin["id"])==meta and cms.count(pin["id"])==pin["rows"],
            "publisher metadata changed")
    return payload

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory",type=Path)
    p.add_argument("--provider",type=Path)
    p.add_argument("--retrieve-pinned-public",action="store_true")
    p.add_argument("--audit",type=Path,required=True)
    a=p.parse_args()
    require(not a.audit.exists(), "audit already exists")
    require((a.retrieve_pinned_public and not a.directory and not a.provider) or
            (not a.retrieve_pinned_public and a.directory and a.provider), "choose exactly one input mode")
    pin=pins()
    d=retrieve(pin["directory"]) if a.retrieve_pinned_public else read_local(a.directory,pin["directory"])
    q=retrieve(pin["provider"]) if a.retrieve_pinned_public else read_local(a.provider,pin["provider"])
    result=screen(d,q,pin["directory"]["rows"],pin["provider"]["rows"])
    result.update({"source_id":"FS-042","release":RELEASE,"pins":pin,
                   "input_mode":"publisher" if a.retrieve_pinned_public else "verified_local",
                   "publisher_reuse_basis":{"dictionary":"https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/long_term_care_hospital/LTCH_Data_Dictionary.pdf",
                   "version":"8.0 September 2026; printed page 4 (footer June 2026)",
                   "scope":"CMS states its Care Compare/PDC government data are public domain, with attribution encouraged and no implied endorsement.",
                   "application_clearance":"pending"}})
    with a.audit.open("x",encoding="utf-8") as out:
        json.dump(result,out,indent=2,sort_keys=True)
        out.write("\n")
    print("FS042_LINKAGE_AGGREGATE",json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    try:
        main()
    except Exception as error:
        print("FS042_LINKAGE_FAILED",type(error).__name__,flush=True)
        raise SystemExit(1) from None
