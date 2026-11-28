"""FS-040: bounded aggregate-only CMS hospital HAI source screening.

No provider-level output, clinical score export, facility risk ranking or Azure.
The national reference is not a measured pooled infection rate.
"""
import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import collect_cms as cms

RELEASE = "2026-11-12"
MODIFIED = "2026-10-19"
NATIONAL = "yd3s-jyhd"
PROVIDER = "77hc-ibv8"
NATIONAL_HEADER = ["Measure ID", "Measure Name", "Score", "Footnote", "Start Date", "End Date"]
PROVIDER_HEADER = ["Facility ID", "Facility Name", "Address", "City/Town", "State", "ZIP Code",
                   "County/Parish", "Telephone Number", "Measure ID", "Measure Name",
                   "Compared to National", "Score", "Footnote", "Start Date", "End Date"]
CODES = {f"HAI_{i}_SIR" for i in range(1, 7)}
WINDOW = ("01/01/2025", "12/31/2025")
MISSING = {"", "not available", "not applicable", "n/a", "na", "-", "--"}
MAX_BYTES = {NATIONAL: 256_000, PROVIDER: 80_000_000}
EXPECTED = {NATIONAL: 6, PROVIDER: 172_332}

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def score_state(value):
    v = value.strip()
    if v.casefold() in MISSING:
        return "missing"
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", v):
        return "unresolved_format"
    try:
        n = Decimal(v)
    except InvalidOperation:
        return "unresolved_format"
    return "reported_zero" if n == 0 else "reported_nonzero"

def read_rows(stream, header):
    reader = csv.reader(stream, strict=True)
    require(next(reader, None) == header, "publisher header drift")
    for row in reader:
        require(len(row) == len(header), "publisher row width drift")
        yield [v.strip() for v in row]

def national(stream):
    seen = set()
    for code, name, score, footnote, start, end in read_rows(stream, NATIONAL_HEADER):
        require(code in CODES and code not in seen, "national reference code drift")
        require(bool(name) and score_state(score) == "reported_nonzero", "national value missing")
        require(Decimal(score) == 1 and footnote == "", "national reference changed")
        require((start, end) == WINDOW, "national reporting period drift")
        seen.add(code)
    require(seen == CODES, "national reference coverage")
    return {"rows": len(seen), "columns": 6, "unit_reference_rows": len(seen),
            "reporting_period": ["2025-01-01", "2025-12-31"],
            "scope": "publisher national reference only, not pooled observed incidence"}

def provider(stream, expected):
    keys, ids, states, measures = set(), set(), set(), set()
    values, periods, field_presence = Counter(), Counter(), Counter()
    repeated = 0
    n = 0
    for n, row in enumerate(read_rows(stream, PROVIDER_HEADER), 1):
        require(n <= expected, "provider row count exceeds pin")
        ident, state, code, score, foot, start, end = (row[i] for i in (0, 4, 8, 11, 12, 13, 14))
        # Unknown ID shapes fail closed; no numeric normalization or parent inference.
        require(bool(re.fullmatch(r"[A-Z0-9]{6}", ident)), "unresolved facility identifier shape")
        require(bool(re.fullmatch(r"[A-Z]{2}", state)), "unresolved state token shape")
        require(bool(re.fullmatch(r"HAI_[1-6]_[A-Z0-9_]+", code)), "unresolved measure code shape")
        key = (ident, code, start, end)
        repeated += key in keys
        keys.add(key); ids.add(ident); states.add(state); measures.add(code)
        values[score_state(score)] += 1
        try:
            a, z = (datetime.strptime(v, "%m/%d/%Y").date() for v in (start, end))
            periods["ordered" if a <= z else "unresolved"] += 1
        except ValueError:
            periods["unresolved"] += 1
        for field, val in zip(PROVIDER_HEADER, row):
            field_presence[field] += bool(val)
    require(n == expected and n == len(keys) + repeated, "provider reconciliation")
    require(sum(values.values()) == sum(periods.values()) == n, "aggregate reconciliation")
    return {"rows": n, "columns": len(PROVIDER_HEADER), "distinct_identifier_tokens": len(ids),
            "distinct_state_tokens": len(states), "distinct_measure_codes": len(measures),
            "repeated_provisional_keys": repeated, "score_states": dict(values),
            "period_states": dict(periods), "nonblank_counts": dict(field_presence),
            "scope": "structural screening only, no facility or measure-specific values"}

def download(ident):
    meta = cms.metadata(ident)
    require(meta["released"] == RELEASE and meta["modified"] == MODIFIED, "publisher release drift")
    require(cms.count(ident) == EXPECTED[ident], "publisher count drift")
    with cms.response(meta["url"]) as resp:
        require(resp.geturl() == meta["url"], "unexpected distribution redirect")
        data = resp.read(MAX_BYTES[ident] + 1)
    require(0 < len(data) <= MAX_BYTES[ident], "download size bound")
    require(cms.metadata(ident) == meta and cms.count(ident) == EXPECTED[ident], "publisher changed during read")
    stream = io.StringIO(data.decode("utf-8-sig"), newline="")
    result = national(stream) if ident == NATIONAL else provider(stream, EXPECTED[ident])
    return {"metadata": meta, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "summary": result}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scope", choices=("national", "provider"), required=True)
    p.add_argument("--audit", type=Path, required=True)
    args = p.parse_args()
    require(not args.audit.exists(), "audit already exists")
    result = download(NATIONAL if args.scope == "national" else PROVIDER)
    audit = {"source_id": "FS-040", "retrieved_utc": datetime.now(timezone.utc).isoformat(),
             "result": result, "retained_rows": 0, "public_promotion": False,
             "reuse_review": "pending", "clinical_or_property_inference": False}
    with args.audit.open("x", encoding="utf-8") as out:
        json.dump(audit, out, indent=2, sort_keys=True)
        out.write("\n")
    print("FS040_AGGREGATE", json.dumps(audit, sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
