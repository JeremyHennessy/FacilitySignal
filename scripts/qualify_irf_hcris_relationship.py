"""Reproduce an aggregate-only, exact FY2024 CMS HCRIS IRF relationship audit."""

import argparse
import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from scripts import qualify_irf_parent_candidates as directory

URL = "https://downloads.cms.gov/Files/hcris/HOSP10FY2024.zip"
CATALOG = "https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/cost-reports-fiscal-year/hospital-2010-fy-2024"
ZIP_BYTES = 135705434
ZIP_HASH = "291749abb7dca4d20aa93e7a5f6c560c4052206a626b8755963a7891b0dc8af2"
MEMBERS = {
    "HOSP10_2024_rpt.csv": (584815, "cedff978"),
    "HOSP10_2024_alpha.csv": (145534467, "3662afce"),
    "HOSP10_2024_nmrc.csv": (673482184, "162c94e6"),
}
FORM = "https://www.cms.gov/files/document/r21p240f.pdf"
INSTRUCTIONS = "https://www.cms.gov/files/document/r21p240i.pdf"
REV21_START = date(2023, 8, 1)
CCN = re.compile(r"[A-Z0-9]{6}")
REPORT_KEY = re.compile(r"[0-9]{1,20}")
W = "S200001"
COORDS = {
    (W, "00300", "00200"): "parent", (W, "00500", "00100"): "unit_name",
    (W, "00500", "00200"): "unit", (W, "00500", "00300"): "unit_cbsa",
    (W, "00500", "00500"): "unit_certification_date",
}
TYPE_COORD = (W, "00500", "00400")
FRAMES = {"lettered_third": re.compile(r"[0-9]{2}[A-Z][0-9]{3}"),
          "lettered_third_fourth": re.compile(r"[0-9]{2}[A-Z]{2}[0-9]{2}")}


def pinned(path):
    with path.open("rb") as f:
        if path.stat().st_size != ZIP_BYTES or hashlib.file_digest(f, "sha256").hexdigest() != ZIP_HASH:
            raise ValueError("FY2024 HCRIS ZIP edition mismatch")


def formatted_date(value):
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            return date.fromisoformat(value)
        if re.fullmatch(r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}", value):
            return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        pass
    return None


def alpha_rows(z, name):
    with z.open(name) as raw, io.TextIOWrapper(raw, encoding="latin-1", newline="") as f:
        yield from csv.reader(f, strict=True)


def load_reports(z):
    out = {}
    for r in alpha_rows(z, "HOSP10_2024_rpt.csv"):
        if len(r) != 18 or not REPORT_KEY.fullmatch(r[0]) or r[0] in out:
            raise ValueError("unexpected report identity or row width")
        # RPT flat-file layout: report key, provider number, status, fiscal begin/end.
        out[r[0]] = (r[2], r[4], r[5], r[6])
    if len(out) != 6113:
        raise ValueError("unexpected report count")
    return out


def load_alpha(z):
    cells = defaultdict(lambda: defaultdict(list))
    n = 0
    for n, r in enumerate(alpha_rows(z, "HOSP10_2024_alpha.csv"), 1):
        if len(r) != 5:
            raise ValueError("unexpected alpha row width")
        if (field := COORDS.get(tuple(r[1:4]))) is not None:
            cells[r[0]][field].append(r[4])
    if n != 3763488:
        raise ValueError("unexpected Alpha row count")
    return cells, n


def load_numeric_type(z):
    result = defaultdict(list)
    marker = b",S200001,00500,00400,"
    with z.open("HOSP10_2024_nmrc.csv") as raw:
        for line in raw:
            # Check only the five-column numeric coordinate, not financial cells.
            if marker in line:
                key, wk, ln, col, val = line.rstrip(b"\r\n").split(b",", 4)
                if (wk, ln, col) == tuple(x.encode("ascii") for x in TYPE_COORD):
                    result[key.decode("ascii")].append(val.decode("ascii"))
    return result


def classify(header, fields, codes):
    report_ccn, status, raw_begin, raw_end = header
    child = fields.get("unit", ())
    if not child or child == [""]:
        return "unit_ccn_not_reported", None
    if len(child) != 1:
        return "duplicate_unit_ccn", None
    parent = fields.get("parent", ())
    if parent != [report_ccn]:
        return "parent_ccn_missing_duplicate_or_header_mismatch", None
    ccn = child[0]
    if not CCN.fullmatch(report_ccn) or not CCN.fullmatch(ccn) or ccn == report_ccn:
        return "invalid_or_nondistinct_ccn", None
    begin, end = formatted_date(raw_begin), formatted_date(raw_end)
    if not begin or not end or begin >= end:
        return "invalid_or_reversed_report_period", None
    if begin < REV21_START:
        return "before_reviewed_worksheet_version", None
    shape = next((label for label, pattern in FRAMES.items() if pattern.fullmatch(ccn)), "other_six_char")
    cert = fields.get("unit_certification_date", ())
    cert_dt = formatted_date(cert[0]) if len(cert) == 1 else None
    companion = all(len(fields.get(k, ())) == 1 and fields[k][0].strip()
                    for k in ("unit_name", "unit_cbsa"))
    if len(codes) != 1 or codes[0] != "5":
        strength = "provider_type_not_single_rehabilitation_5"
    elif not companion or not cert_dt or cert_dt > end:
        strength = "companion_or_certification_date_unresolved"
    else:
        strength = "type5_and_report_companions_corroborated"
    return "literal_distinct_pair", (report_ccn, ccn, begin, end, status, shape, strength)


def candidate_counts(candidates, observations, parents, corroborated):
    scopes = Counter()
    for unit, parent in candidates.items():
        key = (parent, unit)
        if key in observations:
            shape = next((label for label, pattern in FRAMES.items() if pattern.fullmatch(unit)), "other_six_char")
            scopes["exact_pair_" + shape] += 1
            if key in corroborated:
                scopes["companion_corroborated"] += 1
            if len(parents[unit]) > 1:
                scopes["exact_pair_with_alternative_parent"] += 1
        elif unit in parents:
            scopes["only_alternate_parent"] += 1
        else:
            scopes["unit_not_returned_in_literal_pairs"] += 1
    return {"requested_candidates": len(candidates), "outcomes": dict(scopes)}


def directory_cohorts(irf, parent_rows):
    index = defaultdict(list)
    for row in parent_rows:
        index[row["ccn"]].append(row)
    all_keys, uniquely_located_source = {}, {}
    for row in irf:
        unit = row["ccn"]
        parent = directory.candidate(unit)[1]
        if parent is None:
            continue
        if unit in all_keys:
            raise ValueError("duplicate candidate IRF key")
        all_keys[unit] = parent
        if sum(directory.equal(x, row, ("state",)) for x in index[parent]) == 1:
            uniquely_located_source[unit] = parent
    return {"all_literal_identifier_candidates": all_keys,
            "single_same_state_directory_parent_candidates": uniquely_located_source}


def report_summary(headers, alpha, types, candidate_scopes):
    if (alpha.keys() | types.keys()) - headers.keys():
        raise ValueError("unlinked target coordinates")
    outcomes, strengths, status_lit, shapes, type_lit = Counter(), Counter(), Counter(), Counter(), Counter()
    observations = defaultdict(list)
    corroborated = set()
    for key, header in headers.items():
        result, detail = classify(header, alpha.get(key, {}), types.get(key, ()))
        outcomes[result] += 1
        if detail is None:
            continue
        parent, unit, begin, end, status, shape, strength = detail
        strengths[strength] += 1
        status_lit[status] += 1
        codes = types.get(key, ())
        type_lit[codes[0] if len(codes) == 1 else "missing_or_duplicate"] += 1
        shapes[shape] += 1
        observations[(parent, unit)].append((begin, end))
        if strength == "type5_and_report_companions_corroborated":
            corroborated.add((parent, unit))
    parents = defaultdict(set)
    for parent, child in observations:
        parents[child].add(parent)
    same_period = period_overlaps = 0
    conflict_units = set()
    for unit, options in parents.items():
        records = [(p, a, b) for p in options for a, b in observations[p, unit]]
        for i, (parent, start, end) in enumerate(records):
            for p, a, b in records[:i]:
                if (start, end) == (a, b) and parent == p:
                    same_period += 1
                elif start <= b and a <= end:
                    if parent == p:
                        period_overlaps += 1
                    else:
                        conflict_units.add(unit)
    return {
        "report_rows": len(headers), "report_outcomes": dict(outcomes),
        "literal_pair_rows": outcomes["literal_distinct_pair"],
        "literal_distinct_pairs": len(observations), "distinct_child_ccns": len(parents),
        "literal_report_status_codes": dict(status_lit), "literal_ccn_shape_rows": dict(shapes),
        "report_companion_qualification": dict(strengths), "literal_numeric_type_codes": dict(type_lit),
        "companion_corroborated_distinct_pairs": len(corroborated),
        "repeated_pair_keys": sum(len(v) > 1 for v in observations.values()),
        "same_pair_same_period_observation_pairs": same_period,
        "same_pair_nonidentical_overlapping_period_observation_pairs": period_overlaps,
        "child_ccns_with_multiple_parents": sum(len(p) > 1 for p in parents.values()),
        "child_ccns_with_overlapping_periods_across_parents": len(conflict_units),
        "candidate_comparisons": {name: candidate_counts(scope, observations, parents, corroborated)
                                  for name, scope in candidate_scopes.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    try:
        pinned(args.archive)
        with zipfile.ZipFile(args.archive) as z:
            inventory = {x.filename: (x.file_size, f"{x.CRC:08x}") for x in z.infolist()}
            if len(z.infolist()) != len(MEMBERS) or inventory != MEMBERS:
                raise ValueError("unexpected ZIP member inventory")
            headers = load_reports(z)
            alpha, n = load_alpha(z)
            types = load_numeric_type(z)
        irf = directory.load("rehabilitation")
        candidates = directory_cohorts(irf, directory.load("hospital") + directory.load("long-term-hospital"))
        if [len(v) for v in candidates.values()] != [810, 809]:
            raise ValueError("prior candidate scope changed")
        report = report_summary(headers, alpha, types, candidates)
    except (OSError, ValueError, csv.Error, zipfile.BadZipFile):
        parser.exit(2, "Historical HCRIS IRF audit failed; no receipt produced.\n")
    report.update({
        "archive": {"catalog": CATALOG, "url": URL, "bytes": ZIP_BYTES, "sha256": ZIP_HASH,
                    "publisher_last_modified_utc": "2026-10-05T23:50:08Z", "members_bytes_crc32": MEMBERS},
        "alpha_screened_rows": n, "numeric_target_coordinate_rows": sum(map(len, types.values())),
        "alpha_coordinates": {k: list(c) for c, k in COORDS.items()}, "numeric_type_coordinate": TYPE_COORD,
        "period_layout_guard": REV21_START.isoformat(), "period_appropriate_form": FORM, "form_instructions": INSTRUCTIONS,
        "report_table_reference": "https://resdac.org/articles/medicare-cost-report-data-using-link-specifications-microsoft-access-when-importing-data",
        "candidate_lineage": "research/fs043_irf_parent_candidate_audit_20261128.json",
        "application_clearance": "pending", "raw_provider_rows_or_values_retained": 0,
        "limits": [
            "Historical hospital-reported worksheet relationship only. No current status, ownership, legal operator, shared property, capacity, or coverage claims.",
            "Numeric member read only for the single provider-type coordinate; financial data not selected, stored or interpreted.",
            "Reporting, certification, and publisher edition dates are separate. Archive is a status-selected release, not every filing or revision.",
            "Preserve literal six-character keys including two-letter shapes; no pair, location or regulatory status may be inferred from syntax.",
            "The later directory has 810 identifier candidates but 809 single same-state directory parent rows. An exact report pair can corroborate the CCN without choosing a directory site.",
            "Directory comparisons are evidence across releases, not retrospective or current-status imputation.",
        ],
    })
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
