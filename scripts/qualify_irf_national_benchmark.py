"""Qualify one national IRF benchmark release, no facility-level rows or Azure.

Dictionary: IRF QRP v7.0 September 2026, Tables 5 and 8, pp. 9, 17-19.
Counts, rates and ratios are separate; no pooled score or regulatory inference.
"""
import argparse
import csv
import hashlib
import io
import json
import re
from urllib.error import HTTPError
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import collect_cms as cms

ID = "nasn-k89k"
RELEASE = "2026-09-23"
MODIFIED = "2026-08-12"
URL = ("https://data.cms.gov/provider-data/sites/default/files/resources/"
       "0020c7a3fb7a3896384ec099d834641f_1788977188/"
       "Inpatient_Rehabilitation_Facility-National_Data_Sep2026.csv")
DICTIONARY = "https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/inpatient/IRF_Data_Dictionary.pdf"
HEADER = ["CMS Certification Number (CCN)", "Measure Code", "Score", "Footnote",
          "Start Date", "End Date", "Measure Date Range"]
MAX_BYTES = 256 * 1024
MISSING = {"", "-", "--", "not available", "not applicable", "n/a", "na", "null"}
RATES = {p + "_NATL_OBS_RATE" for p in (
    "I_011_05", "I_012_06", "I_013_01", "I_016_01", "I_017_01_PPR_PD",
    "I_018_01_PPR_WI", "I_019_02_DTC", "I_021_01", "I_022_01",
    "I_024_01", "I_025_02", "I_026_01")}
COUNTS = {p + "_" + s for p in ("I_017_01_PPR_PD", "I_018_01_PPR_WI", "I_019_02_DTC")
          for s in ("N_BETTER_NATL", "N_NO_DIFF_NATL", "N_TOO_SMALL", "N_WORSE_NATL")}
RATIOS = {"I_006_01_NATL_SIR", "I_015_01_NATL_SIR", "I_020_01_NATL_MSPB_SCORE"}
# Table 8 contains a typographical space before the I_016_01 suffix;
# only the canonical underscore spelling is accepted. Preserve unknowns.
CODES = {**dict.fromkeys(RATES, "rate"), **dict.fromkeys(COUNTS, "provider_count"),
         **dict.fromkeys(RATIOS, "ratio_or_index")}

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def absent(v):
    return v.strip().casefold() in MISSING

def parse_date(v):
    return datetime.strptime(v.strip(), "%m/%d/%Y").date()

def score_state(v, family):
    if absent(v):
        return "missing"
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", v.strip()):
        return "unresolved_numeric_format"
    n = Decimal(v.strip())
    if family == "provider_count" and n != n.to_integral_value():
        return "unresolved_count"
    if family == "rate" and n > 100:
        return "unresolved_rate"
    return "reported_zero" if n == 0 else "reported_nonzero"

def screen(stream, expected):
    require(type(expected) is int and 0 < expected <= 100, "row bound")
    reader = csv.reader(stream, strict=True)
    require(next(reader, None) == HEADER, "national header drift")
    n = 0
    codes, keys, families, scores, windows, footnotes = set(), set(), Counter(), Counter(), Counter(), Counter()
    unknown = 0
    mspb_window = None
    for n, row in enumerate(reader, 1):
        require(n <= expected and len(row) == len(HEADER), "row width/count drift")
        ident, code, score, foot, start, end, split = (x.strip() for x in row)
        require(ident == "Nation", "national sentinel drift")
        require(bool(re.fullmatch(r"[A-Z0-9_]{1,100}", code)), "measure code shape drift")
        key = (code, start, end, split)
        require(key not in keys, "duplicate reporting key")
        keys.add(key)
        codes.add(code)
        family = CODES.get(code, "unreviewed")
        families[family] += 1
        unknown += family == "unreviewed"
        scores[family + ":" + score_state(score, family)] += 1
        footnotes["absent" if absent(foot) else "unreviewed_present"] += 1
        try:
            a, z = parse_date(start), parse_date(end)
            state = "ordered_contiguous" if a <= z and absent(split) else "unresolved"
        except ValueError:
            state = "unresolved"
        windows[state] += 1
        if code == "I_020_01_NATL_MSPB_SCORE" and state == "ordered_contiguous":
            require(mspb_window is None, "ambiguous spending benchmark period")
            mspb_window = [a.isoformat(), z.isoformat()]
    require(n == expected == len(keys), "row reconciliation")
    require(all(sum(x.values()) == n for x in (families, scores, windows, footnotes)), "aggregate reconciliation")
    return {"rows": n, "columns": len(HEADER), "distinct_codes": len(codes),
            "documented_codes": len(CODES), "unknown_code_rows": unknown,
            "documented_codes_not_observed": len(set(CODES) - codes),
            "distinct_reporting_keys": len(keys), "measure_families": dict(families),
            "score_states": dict(scores), "window_states": dict(windows),
            "footnote_states": dict(footnotes), "mspb_window": mspb_window,
            "semantic_screen_pass": unknown == 0 and codes == set(CODES)
            and windows.get("unresolved", 0) == 0
            and footnotes.get("unreviewed_present", 0) == 0
            and not any(":unresolved" in x for x in scores)}

def checked(stage, operation):
    """Report only fixed stage names and HTTP status, never response bodies."""
    try:
        return operation()
    except Exception as exc:
        cause = exc
        while cause.__cause__ is not None:
            cause = cause.__cause__
        status = cause.code if isinstance(cause, HTTPError) else None
        print("FS043_NATIONAL_STAGE_FAILED", stage, type(cause).__name__, status, flush=True)
        raise


def acquire():
    meta = checked("initial_metadata", lambda: cms.metadata(ID))
    require(meta == {"id": ID, "released": RELEASE, "modified": MODIFIED, "url": URL}, "publisher metadata drift")
    expected = checked("initial_count", lambda: cms.count(ID))
    require(0 < expected <= 100, "publisher count bound")
    with checked("csv_open", lambda: cms.response(URL)) as response:
        require(response.geturl() == URL, "unexpected redirect")
        raw = response.read(MAX_BYTES + 1)
    require(0 < len(raw) <= MAX_BYTES, "source byte bound")
    require(checked("final_metadata", lambda: cms.metadata(ID)) == meta
            and checked("final_count", lambda: cms.count(ID)) == expected, "publisher release changed")
    result = screen(io.StringIO(raw.decode("utf-8-sig"), newline=""), expected)
    return {**result, "publisher": {**meta, "bytes": len(raw),
                                    "sha256": hashlib.sha256(raw).hexdigest()},
            "dictionary": DICTIONARY, "dictionary_version": "7.0",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "scope": "national benchmark only; not a provider or property record; no public clinical comparison or row retention",
            "new_retained_database_rows": 0, "azure_calls": 0}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    require(not args.audit.exists(), "audit exists")
    result = acquire()
    with args.audit.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
    print("FS043_NATIONAL_BENCHMARK", json.dumps(result, sort_keys=True), flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FS043_NATIONAL_BENCHMARK_FAILED", type(exc).__name__, flush=True)
        raise SystemExit(1) from None
