"""Audit complete approved CMS directory packs, without emitting any location or ID."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

PINS={
    "manifest":"34bea799c8f3e1d7e70d0c28688ef9772ff34441",
    "hospital":"b0f0c73946064b5cb754912f685d2fcf975fb02b",
    "long-term-hospital":"4e7e88646adba0076bb6c46e1bd9bfedfa280e48",
}
EDITIONS={"hospital":"2026-11-12","long-term-hospital":"2026-09-23"}

def git_blob(raw):
    return hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()

def site(row):
    return tuple(row[k] for k in ("address","city","state","zip"))

def cohort(pack,expected):
    source=pack["source"]
    if source not in EDITIONS or pack["release"]!=EDITIONS[source]:
        raise ValueError("Directory edition drift")
    if pack["row_count"]!=expected or len(pack["records"])!=expected:
        raise ValueError("Directory count drift")
    out={}
    for row in pack["records"]:
        id_=row["ccn"]
        if not re.fullmatch(r"[0-9A-Z]{6}",id_) or id_ in out or not all(
            isinstance(value,str) and value.strip() for value in site(row)
        ):
            raise ValueError("Ambiguous identity or incomplete site key")
        out[id_]=row
    return out

def audit(hospital,ltch):
    counts=Counter()
    for id_ in hospital.keys() & ltch.keys():
        h,l=hospital[id_],ltch[id_]
        if h["state"]!=l["state"]:
            bucket="ccn_state_conflict"
        elif site(h)==site(l):
            bucket="ccn_state_literal_site"
        elif site(h)[1:]==site(l)[1:] and l["address"]==h["address"]+" -":
            bucket="ccn_state_ltch_terminal_dash_only"
        else:
            bucket="ccn_state_other_site_difference"
        counts[bucket]+=1
    # Distinct literal keys; overlap does not establish any common identity.
    common_sites={site(r) for r in hospital.values()} & {site(r) for r in ltch.values()}
    return {"same_ccn_candidates_by_address_state":dict(counts),"exact_literal_site_keys_present_in_both_packs":len(common_sites),
            "distinct_ccn_values_by_source":{"hospital":len(hospital),"long-term-hospital":len(ltch)},
            "canonical_facility_or_location_merges":0,"address_or_provider_rows_emitted":0}

def profile(root):
    packs={}
    hashes={}
    for source,pin in PINS.items():
        path=root/(source+".json")
        if not path.is_file() or path.is_symlink() or path.stat().st_size>2_000_000:
            raise ValueError("Expected bounded approved pack")
        raw=path.read_bytes()
        if git_blob(raw)!=pin:
            raise ValueError("Approved Git blob mismatch")
        hashes[source]={"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),"git_blob":pin}
        packs[source]=json.loads(raw)
    counts=packs["manifest"]["sources"]
    h=cohort(packs["hospital"],counts["hospital"]["published_records"])
    l=cohort(packs["long-term-hospital"],counts["long-term-hospital"]["published_records"])
    return {**audit(h,l),"release_dates":EDITIONS,"verified_directories":hashes,
            "scope":"Complete approved FacilitySignal packs at distinct publisher release dates. Candidate comparison only; same CCN does not prove current physical site or shared operations."}

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pack_directory",type=Path)
    print(json.dumps(profile(p.parse_args().pack_directory),indent=2,sort_keys=True))
