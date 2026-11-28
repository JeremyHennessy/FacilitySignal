"""Offline, aggregate-only audit of two historical public QIES API projections."""

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from scripts import qualify_reh_predecessors as pred

VERSIONS = {
    "q4_2024": "8143cbc7-484f-438b-9dfa-2e81d5d6a1ed",
    "q1_2025": "315bbdac-3888-43d9-9012-a9a2e29ca179",
}
PINS = {
    "q4_2024_cohort": (9813, "862aa2c639b85692ca70048a91e0f8649c2bc8aac73ec062638be9d04e77fa79"),
    "q4_2024_typed": (7713, "aefc051d70e940b595eba2f092bed66baac7f1cd18f3206a2211fb051ef416a4"),
    "q1_2025_cohort": (10453, "7b3c49185aba769653fed0254a590da8fa442c2d5ccf77a163809c3be7643d6d"),
    "q1_2025_typed": (8337, "808d13e97c2a4a9a783ddbdabbbf3a7cc672c32136af917b5d343fef4b39e09c"),
}
COLUMNS = ("PRVDR_NUM", "STATE_CD", "PRVDR_CTGRY_CD", "PRVDR_CTGRY_SBTYP_CD", "GNRL_FAC_TYPE_CD",
           "CRTFCTN_DT", "ORGNL_PRTCPTN_DT", "PGM_TRMNTN_CD", "TRMNTN_EXPRTN_DT")
DATE_COLUMNS = ("CRTFCTN_DT", "ORGNL_PRTCPTN_DT", "TRMNTN_EXPRTN_DT")
MAX_ROWS = 200
REH_TYPE = ("01", "28")


def load(path, role):
    size, digest = PINS[role]
    with path.open("rb") as source:
        raw = source.read(size + 1)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("QIES projection pin mismatch")
    return json.loads(raw)


def reported_date(value):
    if value in ("", "00000000"):
        return None
    if not re.fullmatch(r"[0-9]{8}", value):
        raise ValueError("noncanonical QIES date")
    return datetime.strptime(value, "%Y%m%d").date()


def type_key(row):
    return row["PRVDR_CTGRY_CD"], row["PRVDR_CTGRY_SBTYP_CD"]


def validate(rows, requested=None):
    if not isinstance(rows, list) or len(rows) >= MAX_ROWS:
        raise ValueError("unexpected or potentially truncated QIES response")
    result = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(COLUMNS) or not all(isinstance(v, str) for v in row.values()):
            raise ValueError("unexpected QIES column or cell type")
        ccn, state = row["PRVDR_NUM"], row["STATE_CD"]
        if not pred.HISTORICAL_CCN.fullmatch(ccn) or not pred.pecos.STATE.fullmatch(state):
            raise ValueError("invalid QIES CCN/state syntax")
        if (requested is not None and ccn not in requested) or (requested is None and type_key(row) != REH_TYPE):
            raise ValueError("QIES query returned a row outside scope")
        for col in DATE_COLUMNS:
            reported_date(row[col])
        result[ccn].append(row)
    return result


def summarise(scope, by_ccn):
    statuses, types, general, termination = Counter(), Counter(), Counter(), Counter()
    dates = {col: Counter() for col in DATE_COLUMNS}
    before_both = typed_hits = clocks_differ = lettered_absent = 0
    for ccn, state in scope.items():
        candidates = by_ccn.get(ccn, ())
        if not candidates:
            statuses["not_returned"] += 1
            lettered_absent += not ccn.isdecimal()
            continue
        if len(candidates) != 1:
            statuses["multiple_exact_ccn_rows"] += 1
            continue
        row = candidates[0]
        if row["STATE_CD"] != state:
            statuses["state_conflict"] += 1
            continue
        statuses["exact_ccn_and_state"] += 1
        types["/".join(type_key(row))] += 1
        general[row["GNRL_FAC_TYPE_CD"] or "blank"] += 1
        termination[row["PGM_TRMNTN_CD"] or "blank"] += 1
        observed = {k: reported_date(row[k]) for k in DATE_COLUMNS}
        for col, dt in observed.items():
            label = ("blank" if row[col] == "" else "literal_zero" if dt is None else
                     "on_or_before_2024_end" if dt <= pred.pecos.CUTOFF else "after_2024_end")
            dates[col][label] += 1
        cert, orig = (observed[k] for k in DATE_COLUMNS[:2])
        clocks_differ += cert is not None and orig is not None and cert != orig
        if type_key(row) == REH_TYPE:
            typed_hits += 1
            before_both += bool(cert and orig and max(cert, orig) <= pred.pecos.CUTOFF)
    return {
        "requested_ccns": len(scope), "match_outcomes": {key: statuses[key] for key in
            ("exact_ccn_and_state", "not_returned", "multiple_exact_ccn_rows", "state_conflict")},
        "lettered_ccns_not_returned": lettered_absent, "literal_category_subtype": dict(types),
        "literal_general_type": dict(general), "literal_termination_code": dict(termination),
        "literal_date_buckets": {k: dict(v) for k, v in dates.items()},
        "reported_certification_and_original_participation_dates_differ": clocks_differ,
        "typed_01_28_exact_matches": typed_hits,
        "typed_exact_matches_with_both_reported_dates_by_2024_end": before_both,
    }


def edition(cohort, typed, scopes):
    requested = set().union(*(d.keys() for d in scopes.values()))
    by_ccn = validate(cohort, requested)
    by_type = validate(typed)
    relevant = lambda rows: Counter(tuple(r[k] for k in COLUMNS) for r in rows
                                    if r["PRVDR_NUM"] in requested and type_key(r) == REH_TYPE)
    if relevant(cohort) != relevant(typed):
        raise ValueError("cohort and independently typed query disagree")
    return {
        "cohort_request_distinct_keys": len(requested), "cohort_response_rows": len(cohort),
        "national_typed_response_rows": len(typed), "national_typed_distinct_exact_ccns": len(by_type),
        "national_typed_general_type_blank": sum(not r["GNRL_FAC_TYPE_CD"] for r in typed),
        "national_typed_literal_termination_code": dict(Counter(r["PGM_TRMNTN_CD"] or "blank" for r in typed)),
        "typed_projection_overlap_checks_exact": True,
        **{scope: summarise(keys, by_ccn) for scope, keys in scopes.items()},
    }


def derive_scopes(early, later, measure):
    baseline = pred.compare(early, later, measure)
    op = {r["Facility ID"]: r["State"] for r in measure}
    later_only, former = {}, {}
    archive, _ = pred.historic_index(early)
    for r in later:
        ccn = r["CCN"]
        if (r["PROVIDER TYPE CODE"] != pred.pecos.REH_TYPE or ccn not in op
                or pred.pecos.date_bucket(r["REH CONVERSION DATE"]) != "after_period_end"):
            continue
        state = op[ccn]
        later_only[ccn] = state
        for old in pred.former_ccns(r[pred.FORMER]):
            if old in former or pred.status(archive.get(old, ()), state) not in pred.OUTCOMES[:2]:
                raise ValueError("former key is not uniquely qualified for this scope")
            former[old] = state
    if (len(op), len(later_only), len(former), len(op.keys() | former.keys())) != (49, 14, 22, 71) or baseline[
            "cohort_later_current_ccns_present_in_historical_pecos"] != 0:
        raise ValueError("previous REH cohort baselines changed")
    return {"historical_op36": op, "later_pecos_conversion_subset": later_only, "explicit_former_pecos_ccns": former}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ("early", "later", "op36", *PINS):
        parser.add_argument("--" + role.replace("_", "-"), type=Path, required=True)
    a = parser.parse_args()
    try:
        early = pred.projected_csv(pred.read_early(a.early), "latin-1", pred.EARLY_FIELDS, pred.EARLY_ROWS)
        later = pred.projected_csv(pred.pecos.read_enrollment(a.later), "utf-8-sig",
                                   (*pred.pecos.FIELDS, pred.FORMER), pred.pecos.ENROLL_ROWS)
        measure = pred.op36.records(pred.op36.load_pinned(a.op36, "provider"), pred.op36.PROVIDER_COLUMNS, 49)
        scopes = derive_scopes(early, later, measure)
        editions = {v: edition(*(load(getattr(a, v + "_" + role), v + "_" + role)
                                 for role in ("cohort", "typed")), scopes) for v in VERSIONS}
    except (OSError, ValueError, csv.Error):
        parser.exit(2, "Historical QIES projection verification failed; no receipt produced.\n")
    report = {
        "status": "exact_version_api_projections_qualified",
        "op36_performance_period": ["2024-01-01", "2024-12-31"],
        "q4_edition_catalog_label": "2024-12-02", "q4_catalog_updated": "2025-01-31",
        "editions": editions, "api_dataset_versions": VERSIONS, "projected_columns": COLUMNS,
        "request_recipe": {"endpoint": "https://data.cms.gov/data-api/v1/dataset/{version}/data",
                           "size": MAX_ROWS, "sort": "PRVDR_NUM", "offset": 0,
                           "cohort_filter": "PRVDR_NUM IN the sorted union of 49 OP-36 CCNs and 22 exact former CCNs",
                           "typed_filter": "PRVDR_CTGRY_CD=01 AND PRVDR_CTGRY_SBTYP_CD=28"},
        "projection_response_pins": {key: {"bytes": n, "sha256": h} for key, (n, h) in PINS.items()},
        "q4_catalog": "https://catalog.data.gov/dataset/provider-of-services-file-quality-improvement-and-evaluation-system-2024-12-02",
        "api_schema": "https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/provider-of-services-file-quality-improvement-and-evaluation-system/api-docs",
        "record_layout": "https://data.cms.gov/sites/default/files/2023-07/0ca58d5d-7914-4532-b22d-41741d3e6151/P.QWB.POSQ.OTHER.LAYOUT.MAR23.pdf",
        "reh_certification_memo": "https://www.cms.gov/files/document/qso-24-20-reh-revised-2024-09-06.pdf",
        "pinned_cohort_lineage": "research/reh_predecessors_2024_snapshot_20261128.json",
        "limits": [
            "Public API projections only, not full-file checksums; not returned is not evidence of non-certification.",
            "QIES survey-related certification date, original Medicare and/or Medicaid participation approval, later PECOS REH enrollment approval and OP-36 collection period are separate clocks.",
            "QIES category/subtype is the positive REH label here. A blank general facility type or termination field is not itself a type, status, or eligibility claim.",
            "Chronology contrasts are publisher-field differences; they do not establish operating dates, program eligibility, claims attribution, or the OP-36 count discrepancy.",
            "Lettered former keys are literal; never strip letters or substitute a numeric parent.",
        ],
        "application_clearance": "pending", "provider_rows_or_values_retained": 0,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
