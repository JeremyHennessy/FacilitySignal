"""Reproduce the November 2026 CMS REH OP-36 aggregate-only source receipt offline."""

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

CATALOG = "https://data.cms.gov/provider-data/dataset/"
RESOURCES = "https://data.cms.gov/provider-data/sites/default/files/resources/"
PINS = {
    "provider": ("zez1-ka2w", 13537, "08ef87fe8c8b116e2f32ba53fbdf0c2c79abf38334bb1a750190749a2ff138d4",
                 "8058b83869a5ba155b84c3227e60f61c_1792600032/REH_Unplanned_Hospital_Visits-Hospital.csv"),
    "national": ("uk3n-au7a", 320, "f296d65d98bfa2fe71d58054d30c74f197a9db02213d968a032373ffb6bbdb08",
                 "ab50380fe5f8578c9b07e118dcdc43e4_1792600039/REH_Unplanned_Hospital_Visits-National.csv"),
    "footnotes": ("y9us-9xdf", 3456, "5214e1468fb04c5cdeac8920f2c446cccaa65e2f6f929424cd228042a52d963e",
                  "f29bb7c812e242f6edfef0a4b7d0eaca_1760630713/Footnote_Crosswalk.csv"),
}
MEASURE = "REH_OP_36"
MEASURE_NAME = "Ratio of unplanned hospital visits after hospital outpatient surgery"
PERIOD = ("01/01/2024", "12/31/2024")
NA = "Not Available"
START_END = ("Start Date", "End Date")
MEASURE_FIELDS = ("Measure ID", "Measure Name")
VALUE_FIELDS = ("Denominator", "Score", "Lower Estimate", "Higher Estimate")
PROVIDER_COLUMNS = (
    "Facility ID", "Facility Name", "Address", "City/Town", "State", "ZIP Code",
    "County/Parish", "Telephone Number", *MEASURE_FIELDS, "Compared to National",
    *VALUE_FIELDS, "Footnote", *START_END,
)
NATIONAL_COUNTS = {
    "worse": "Number of Hospitals Worse", "same": "Number of Hospitals Same",
    "better": "Number of Hospitals Better", "too_few": "Number of Hospitals Too Few",
}
NATIONAL_COLUMNS = (*MEASURE_FIELDS, "National Rate", *NATIONAL_COUNTS.values(), "Footnote", *START_END)
FOOTNOTE_COLUMNS = ("Footnote", "Footnote Text")
NOTE_TEXT = {
    "1": "The number of cases/patients is too few to report.",
    "5": "Results are not available for this reporting period.",
    "7": "No cases met the criteria for this measure.",
}
PROVIDER_UNAVAILABLE = {
    ("Number of cases too small", "1"): "too_few",
    (NA, "5"): "period_result_unavailable",
    (NA, "7"): "no_eligible_cases",
}
DECIMAL = re.compile(r"[0-9]+(?:\.[0-9]+)?")
INTEGER = re.compile(r"(?:0|[1-9][0-9]*)")


def load_pinned(path, role):
    _, size, digest, _ = PINS[role]
    with path.open("rb") as source:
        raw = source.read(size + 1)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(role + " input does not match the pinned CMS release")
    return raw


def records(raw, columns, count):
    parsed = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True))
    if (len(parsed) != count + 1 or tuple(parsed[0]) != columns
            or any(len(row) != len(columns) for row in parsed[1:])):
        raise ValueError("unexpected CSV schema, row count or width")
    return [dict(zip(columns, row)) for row in parsed[1:]]


def require_scope(row):
    if (tuple(row[k] for k in MEASURE_FIELDS) != (MEASURE, MEASURE_NAME)
            or tuple(row[k] for k in START_END) != PERIOD):
        raise ValueError("unexpected REH OP-36 measure or performance period")


def qualify_footnotes(rows):
    notes = {r["Footnote"]: r["Footnote Text"] for r in rows}
    if len(rows) != len(notes) or any(notes.get(k) != v for k, v in NOTE_TEXT.items()):
        raise ValueError("footnote crosswalk missing, duplicate, or changed")


def qualify_provider(rows):
    statuses = Counter({"reported_numeric": 0, **dict.fromkeys(PROVIDER_UNAVAILABLE.values(), 0)})
    ids, states = set(), set()
    for row in rows:
        require_scope(row)
        ccn, state = row["Facility ID"], row["State"]
        if not re.fullmatch(r"[0-9]{6}", ccn) or ccn in ids or not re.fullmatch(r"[A-Z]{2}", state):
            raise ValueError("invalid or duplicate provider identity")
        ids.add(ccn)
        states.add(state)
        label = (row["Compared to National"], row["Footnote"])
        values = tuple(row[k] for k in VALUE_FIELDS)
        if label in PROVIDER_UNAVAILABLE and values == (NA,) * len(VALUE_FIELDS):
            statuses[PROVIDER_UNAVAILABLE[label]] += 1
        elif label == ("No Different than expected", "") and all(DECIMAL.fullmatch(v) for v in values):
            denom, score, lower, upper = values
            if not INTEGER.fullmatch(denom) or int(denom) == 0 or not Decimal(lower) <= Decimal(score) <= Decimal(upper):
                raise ValueError("invalid denominator or estimate envelope")
            statuses["reported_numeric"] += 1
        else:
            raise ValueError("unexpected provider comparison, footnote or numeric availability")
    return {
        "rows": len(rows), "distinct_ccns": len(ids), "distinct_state_codes": len(states),
        "score_not_available": len(rows) - statuses["reported_numeric"], "status_counts": dict(statuses),
    }


def qualify_national(row):
    require_scope(row)
    if (row["National Rate"], row["Footnote"]) != (NA, "5"):
        raise ValueError("unexpected national benchmark availability or footnote")
    counts = {}
    for label, field in NATIONAL_COUNTS.items():
        if not INTEGER.fullmatch(row[field]):
            raise ValueError("invalid national comparison count")
        counts[label] = int(row[field])
    return {"rate_status": "period_result_unavailable", "published_comparison_counts": counts}


def qualify(provider, national, footnotes):
    qualify_footnotes(records(footnotes, FOOTNOTE_COLUMNS, 32))
    p = qualify_provider(records(provider, PROVIDER_COLUMNS, 49))
    n = qualify_national(records(national, NATIONAL_COLUMNS, 1)[0])
    provider_comparable = {"worse": 0, "same": p["status_counts"]["reported_numeric"], "better": 0,
                           "too_few": p["status_counts"]["too_few"]}
    matches = provider_comparable == n["published_comparison_counts"]
    return {
        "status": "historical_aggregate_qualified",
        "catalog_release": "2026-11-12",
        "measure_id": MEASURE,
        "measure_window_days": 7,
        "measure_semantics_source": "https://data.cms.gov/provider-data/topics/hospitals/measures-and-current-data-collection-periods",
        "performance_period": ["2024-01-01", "2024-12-31"],
        "sources": {role: {"catalog": CATALOG + cid, "download": RESOURCES + resource, "bytes": size, "sha256": digest}
                    for role, (cid, size, digest, resource) in PINS.items()},
        "provider_export": p,
        "national_export": n,
        "cross_grain_check": {
            "provider_export_comparison_label_counts": provider_comparable,
            "matches_published_national_comparison_counts": matches,
            "difference_explanation": "not established",
            "derivation_or_coverage_population_supported": False,
        },
        "application_clearance": "pending",
        "provider_rows_retained": 0,
        "provider_values_retained": 0,
        "limits": [
            "Provider rows are distinct historical measure records, not the current operating REH population.",
            "National rate unavailable is not zero; a numeric provider result is not a confirmed national benchmark.",
            "Publisher national counts and provider-export labels are different grains; do not reconstruct or impute missing classifications.",
            "Footnote 7 is no eligible cases for this measure, not zero unplanned visits or absence of service.",
            "The CMS measure-specific listing defines seven days; generic file descriptions in the Hospital Downloadable Database dictionary do not define the measure.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for role in PINS:
        parser.add_argument("--" + role, type=Path, required=True)
    args = parser.parse_args()
    try:
        result = qualify(*(load_pinned(getattr(args, role), role) for role in PINS))
    except (OSError, ValueError, csv.Error):
        parser.exit(2, "REH OP-36 input verification failed; no receipt produced.\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
