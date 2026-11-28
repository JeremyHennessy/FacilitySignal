"""Audit publisher-declared former CCNs in a dated 2024 enrollment file, aggregates only."""

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from scripts import qualify_reh_op36 as op36
from scripts import qualify_reh_pecos as pecos

EARLY_DATE = date(2024, 12, 5)
EARLY_ROWS = 9283
EARLY_SIZE = 2593146
EARLY_HASH = "9b1d29f2990f8ed9c9102e5c11c5be49487d64fc39a1f95f67215eaa832eab09"
EARLY_URL = "https://data.cms.gov/sites/default/files/2024-12/0b60b159-56e3-4c48-94e6-15d11eb3f1d0/Hospital_Enrollments_2024.12.05.csv"
EARLY_CATALOG = "https://data.cms.gov/data-api/v1/dataset-resources/be4d4816-be24-4635-9f4b-af9af75b708e"
GUIDANCE = "https://data.cms.gov/sites/default/files/2026-02/Hospital_Data_Guidance.pdf"
EID = re.compile(r"[A-Z0-9]{15}")
# Literal six-character keys in the pinned December comparison; never rewrite lettered keys.
HISTORICAL_CCN = re.compile(r"[0-9]{2}[A-Z0-9][0-9]{3}")
FORMER = "CAH OR HOSPITAL CCN"
TYPE_LABELS = {**pecos.OTHER_TYPES, pecos.REH_TYPE: pecos.REH_LABEL}
EARLY_FIELDS = ("ENROLLMENT ID", "CCN", "ENROLLMENT STATE", "STATE", "PROVIDER TYPE CODE", "PROVIDER TYPE TEXT")
OUTCOMES = ("historical_hospital_00_09", "historical_cah_00_85", "not_in_archive",
            "multiple_historical_enrollments", "state_conflict_or_missing", "historical_type_not_predecessor")


def read_early(path):
    with path.open("rb") as source:
        raw = source.read(EARLY_SIZE + 1)
    if len(raw) != EARLY_SIZE or hashlib.sha256(raw).hexdigest() != EARLY_HASH:
        raise ValueError("historical PECOS source pin mismatch")
    return raw


def projected_csv(raw, encoding, fields, count):
    reader = csv.reader(io.StringIO(raw.decode(encoding), newline=""), strict=True)
    header = next(reader, [])
    if len(header) != 39 or len(set(header)) != len(header) or not set(fields) <= set(header):
        raise ValueError("unexpected enrollment schema")
    positions = {key: header.index(key) for key in fields}
    rows = []
    for row in reader:
        if len(row) != len(header):
            raise ValueError("unexpected enrollment row width")
        rows.append({key: row[index] for key, index in positions.items()})
    if len(rows) != count:
        raise ValueError("unexpected enrollment row count")
    return rows


def historic_index(rows):
    all_ids, types, by_ccn = set(), Counter(), defaultdict(list)
    for r in rows:
        eid, code, label, ccn = (r[key] for key in ("ENROLLMENT ID", "PROVIDER TYPE CODE", "PROVIDER TYPE TEXT", "CCN"))
        if not EID.fullmatch(eid) or eid in all_ids or TYPE_LABELS.get(code) != label:
            raise ValueError("unexpected historical enrollment identity or specialty")
        all_ids.add(eid)
        types[code] += 1
        if HISTORICAL_CCN.fullmatch(ccn):
            by_ccn[ccn].append((code, r["ENROLLMENT STATE"], r["STATE"]))
    return by_ccn, dict(types)


def former_ccns(field):
    tokens = field.split("|") if field else []
    if any(not HISTORICAL_CCN.fullmatch(token) for token in tokens) or len(set(tokens)) != len(tokens):
        raise ValueError("malformed former enrollment identifier field")
    return tokens


def status(candidates, state):
    if not candidates:
        return "not_in_archive"
    if len(candidates) != 1:
        return "multiple_historical_enrollments"
    code, enrollment, practice = candidates[0]
    if (enrollment, practice) != (state, state):
        return "state_conflict_or_missing"
    if code == "00-09":
        return "historical_hospital_00_09"
    if code == "00-85":
        return "historical_cah_00_85"
    return "historical_type_not_predecessor"


def compare(early, later, measure):
    archived, archived_types = historic_index(early)
    typed, other, _, _, _ = pecos.typed_index(later)
    if set(typed) & other:
        raise ValueError("later current CCN reused across specialty codes")
    op36.qualify_provider(measure)
    observed = {row["Facility ID"]: row["State"] for row in measure}
    scope = {c: observed[c] for c in typed.keys() & observed.keys()
             if typed[c][2] == "after_period_end"}
    if any(typed[c][:2] != (state, state) for c, state in scope.items()):
        raise ValueError("later enrollment and historical measure state conflict")

    token_counts, candidates_per_case = Counter(), Counter()
    lettered_token_occurrences = 0
    outcome = dict.fromkeys(OUTCOMES, 0)
    all_tokens, qualified_tokens = set(), set()
    for row in later:
        ccn = row["CCN"]
        if row["PROVIDER TYPE CODE"] != pecos.REH_TYPE or ccn not in scope:
            continue
        tokens = former_ccns(row[FORMER])
        token_counts[len(tokens)] += 1
        qualified = 0
        for token in tokens:
            all_tokens.add(token)
            lettered_token_occurrences += not token.isdecimal()
            result = status(archived.get(token, ()), scope[ccn])
            outcome[result] += 1
            if result in OUTCOMES[:2]:
                qualified += 1
                qualified_tokens.add(token)
        candidates_per_case[qualified] += 1

    return {
        "historical_pecos_file_date": EARLY_DATE.isoformat(),
        "later_pecos_file_date": pecos.SNAPSHOT.isoformat(),
        "op36_performance_period": ["2024-01-01", pecos.CUTOFF.isoformat()],
        "archived_enrollment_rows": sum(archived_types.values()),
        "archived_enrollment_rows_by_specialty": archived_types,
        "cohort_later_typed_op36_ccns_with_reported_conversion_after_2024": len(scope),
        "cohort_later_current_ccns_present_in_historical_pecos": sum(ccn in archived for ccn in scope),
        "later_cases_by_number_of_explicit_former_ccns": dict(token_counts),
        "later_cases_by_number_of_qualified_former_ccns": dict(candidates_per_case),
        "explicit_former_ccn_occurrences": sum(outcome.values()),
        "lettered_exact_former_ccn_occurrences": lettered_token_occurrences,
        "distinct_explicit_former_ccns": len(all_tokens),
        "distinct_qualified_former_ccns": len(qualified_tokens),
        "explicit_former_ccn_occurrences_by_outcome": outcome,
        "limits": [
            "File dates are publisher filename dates; the December export is one snapshot, not full 2024 enrollment history.",
            "Former CCNs come only from the later publisher's explicit predecessor field. Lettered keys stay distinct; no fuzzy, suffix, organization or location match.",
            "Unique historical enrollment, exact former CCN, both state fields and typed hospital/CAH are required. Multiple valid former enrollments remain separate.",
            "Guidance defines the reported conversion date as earliest approved REH enrollment status, not operational date or quality-program eligibility.",
            "Historical predecessor enrollment evidence does not establish OP-36 billable-case attribution, reporting eligibility, site continuity or the cause of the national/provider mismatch.",
        ],
        "application_clearance": "pending",
        "provider_rows_identifiers_or_values_retained": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-enrollment", type=Path, required=True)
    parser.add_argument("--later-enrollment", type=Path, required=True)
    parser.add_argument("--op36-provider", type=Path, required=True)
    args = parser.parse_args()
    try:
        # The historical file is not UTF-8. Decode bytes one-to-one; only typed ASCII keys are interpreted.
        early = projected_csv(read_early(args.historical_enrollment), "latin-1", EARLY_FIELDS, EARLY_ROWS)
        later = projected_csv(pecos.read_enrollment(args.later_enrollment), "utf-8-sig", (*pecos.FIELDS, FORMER), pecos.ENROLL_ROWS)
        history = op36.records(op36.load_pinned(args.op36_provider, "provider"), op36.PROVIDER_COLUMNS, 49)
        report = compare(early, later, history)
    except (OSError, ValueError, csv.Error):
        parser.exit(2, "REH predecessor source verification failed; no receipt produced.\n")
    cid, size, digest, op_path = op36.PINS["provider"]
    report["sources"] = {
        "historical_enrollment": {"catalog_resource": EARLY_CATALOG, "download": EARLY_URL, "bytes": EARLY_SIZE, "sha256": EARLY_HASH},
        "later_enrollment": {"catalog_resource": pecos.CATALOG, "download": pecos.ENROLL_URL,
                             "bytes": pecos.ENROLL_PIN[0], "sha256": pecos.ENROLL_PIN[1]},
        "op36_provider": {"catalog": op36.CATALOG + cid, "download": op36.RESOURCES + op_path, "bytes": size, "sha256": digest},
        "conversion_and_predecessor_field_guidance_sections_3_7_and_5_2": GUIDANCE,
        "historical_ccn_format_guidance_section_2779c": "https://www.cms.gov/regulations-and-guidance/guidance/manuals/downloads/som107c02.pdf",
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
