"""Offline aggregate audit of FY2025 SNF-2024 composite address observations."""

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

CATALOG = "https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/cost-reports-fiscal-year/snf-2024-fy-2025-data-files"
URL = "https://downloads.cms.gov/FILES/HCRIS/SNF24FY2025.ZIP"
PIN = (90890707, "d34ae917f2da83e25c668547589c6da0044fd5852eea8f6bb16567205371d253")
MEMBERS = {
    "SNF24_2025_alpha.csv": (140158016, "c35c5b3e"),
    "SNF24_2025_nmrc.csv": (404092246, "c472c8f7"),
    "SNF24_2025_rollup.csv": (17865554, "19747188"),
    "SNF24_2025_rpt.csv": (1150371, "cf424441"),
}
WORKSHEET = "S200000"
FORM_CHANGE_END_DATE = date(2025, 9, 30)
REPORT_ROWS, ALPHA_ROWS = 11802, 3581725
SCALAR = {("00300", "00300"): "ccn", ("00900", "00100"): "begin", ("00900", "00200"): "end",
          ("01100", "00100"): "distinct_part_flag", ("01200", "00100"): "flag", ("00100", "00100"): "street",
          ("00200", "00100"): "city", ("00200", "00200"): "state", ("00200", "00300"): "zip"}
COLS = {"00100": "name", "00200": "street", "00300": "po_box", "00400": "city", "00500": "state", "00600": "zip"}
REQUIRED = ("name", "street", "city", "state", "zip")
CIVIC = ("street", "city", "state", "zip")
PO = re.compile(r"\b(?:P[. ]*O[. ]*BOX|POST OFFICE BOX)\b", re.I)


def pinned(path):
    with path.open("rb") as source:
        if path.stat().st_size != PIN[0] or hashlib.file_digest(source, "sha256").hexdigest() != PIN[1]:
            raise ValueError("SNF FY2025 archive pin mismatch")


def member_rows(z, path):
    with z.open(path) as raw, io.TextIOWrapper(raw, encoding="latin-1", newline="") as stream:
        yield from csv.reader(stream, strict=True)


def load_reports(rows):
    headers = {}
    for row in rows:
        if len(row) != 18 or not re.fullmatch(r"[0-9]{1,20}", row[0]) or row[0] in headers:
            raise ValueError("duplicate/invalid report identity or row width")
        headers[row[0]] = (row[2], row[4], row[5], row[6])
    return headers


def load_fields(rows):
    scalar = defaultdict(lambda: defaultdict(list))
    locations = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    n = 0
    for n, row in enumerate(rows, 1):
        if len(row) != 5:
            raise ValueError("unexpected Alpha row width")
        key, worksheet, line, col, val = row
        if worksheet != WORKSHEET:
            continue
        if (field := SCALAR.get((line, col))) is not None:
            scalar[key][field].append(val)
        elif re.fullmatch(r"013[0-9]{2}", line):
            if col not in COLS:
                raise ValueError("unrecognized composite address column")
            locations[key][line][COLS[col]].append(val)
    return scalar, locations, n


def use_date(raw):
    if not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", raw):
        return None
    try:
        return datetime.strptime(raw, "%m/%d/%Y").date()
    except ValueError:
        return None


def one(fields, key):
    values = fields.get(key, ())
    return values[0] if len(values) == 1 else ""


def flag_value(fields, field="flag"):
    vals = fields.get(field, ())
    if len(vals) > 1:
        return "duplicate"
    if not vals:
        return "not_reported"
    return vals[0] if vals[0] in ("Y", "N") else "blank_or_unrecognized"


def address_shape(fields):
    if any(len(values) > 1 for values in fields.values()):
        return "duplicate_component_cell"
    if not all(one(fields, k).strip() for k in REQUIRED):
        return "po_box_only_or_missing_street" if one(fields, "po_box").strip() and not one(fields, "street").strip() else "missing_required_cell"
    street, city, state, postal = (one(fields, col) for col in CIVIC)
    if not re.fullmatch(r"[A-Z]{2}", state) or not re.fullmatch(r"[0-9]{5}(?:-[0-9]{4})?", postal):
        return "unqualified_state_or_zip_shape"
    if PO.search(street):
        return "po_box_in_street"
    if not re.search(r"[0-9]", street):
        return "street_without_number_unresolved"
    return "complete_civic_shape"


def report_bounds(header, fields):
    ccn, _, b, e = header
    if not re.fullmatch(r"[0-9]{6}", ccn) or fields.get("ccn") != [ccn]:
        return None, "header_and_worksheet_ccn_unresolved"
    begin, end = use_date(b), use_date(e)
    if begin is None or end is None or begin >= end or end < FORM_CHANGE_END_DATE:
        return None, "invalid_report_period_or_before_form_cutover"
    if fields.get("begin") != [b] or fields.get("end") != [e]:
        return None, "header_and_worksheet_period_unresolved"
    return (begin, end), "exact_header_identity_and_period"


def summarize(headers, scalar, locations):
    if (scalar.keys() | locations.keys()) - headers.keys():
        raise ValueError("unlinked target worksheet cells")
    flags, identity, scopes, y_tiers, main_relation, years = (Counter() for _ in range(6))
    ccn_flags = defaultdict(set)
    providers, qualifying_reports, all_civic, provider_civic = set(), set(), set(), set()
    report_histories = defaultdict(list)
    y_periods = set()
    subscript_counts = Counter()
    status_lit, distinct_flags = Counter(), Counter()
    quality_by_distinct_flag, main_by_distinct_flag = defaultdict(Counter), defaultdict(Counter)
    concordant_reports, concordant_ccns, concordant_tuples = set(), set(), set()
    concordant_observations = 0
    for key, header in headers.items():
        ccn, status, _, raw_end = header
        if (end_date := use_date(raw_end)) is not None:
            years[str(end_date.year)] += 1
        fields, comps = scalar.get(key, {}), locations.get(key, {})
        flag = flag_value(fields)
        distinct_flag = flag_value(fields, "distinct_part_flag")
        flags[flag] += 1
        bounds, gate = report_bounds(header, fields)
        identity[gate] += 1
        if bounds:
            ccn_flags[ccn].add(flag)
        if comps:
            scopes[flag + "_reports_with_any_line13_cells"] += 1
        if flag == "Y":
            distinct_flags[distinct_flag] += 1
            if bounds:
                y_periods.add((ccn, *bounds))
            status_lit[status] += 1
            if not comps:
                y_tiers["no_line13_group"] += 1
                quality_by_distinct_flag[distinct_flag]["no_line13_group"] += 1
        report_civic = set()
        for sub, comp in comps.items():
            shape = address_shape(comp)
            subscript_counts["base_01300" if sub == "01300" else "usages_of_full_nonbase_subscript"] += 1
            if all(one(comp, k).strip() for k in REQUIRED):
                scopes[flag + "_line13_groups_with_required_cells_populated"] += 1
            if flag != "Y":
                continue
            if one(comp, "po_box").strip():
                scopes["Y_line13_groups_with_separate_po_box"] += 1
            if bounds is None:
                y_tiers["header_gate_not_qualified"] += 1
                quality_by_distinct_flag[distinct_flag]["header_gate_not_qualified"] += 1
                continue
            y_tiers[shape] += 1
            quality_by_distinct_flag[distinct_flag][shape] += 1
            if shape != "complete_civic_shape":
                continue
            key_tuple = tuple(one(comp, k) for k in CIVIC)
            primary = tuple(one(fields, k) for k in CIVIC)
            relation = ("main_missing_or_ambiguous" if not all(x.strip() for x in primary) else
                        "exact_same_printed_tuple_as_main" if key_tuple == primary else "different_printed_tuple_than_main")
            main_relation[relation] += 1
            main_by_distinct_flag[distinct_flag][relation] += 1
            if distinct_flag == "Y":
                concordant_reports.add(key)
                concordant_ccns.add(ccn)
                concordant_tuples.add(key_tuple)
                concordant_observations += 1
            providers.add(ccn)
            qualifying_reports.add(key)
            report_civic.add(key_tuple)
            all_civic.add(key_tuple)
            provider_civic.add((ccn, key_tuple))
        if bounds and flag == "Y":
            report_histories[ccn].append((*bounds, frozenset(report_civic)))
    repeated_periods = overlap_disagreement = 0
    for history in report_histories.values():
        for i, (a, b, values) in enumerate(history):
            for c, d, previous in history[:i]:
                repeated_periods += (a, b) == (c, d)
                overlap_disagreement += bool(values and previous and a <= d and c <= b and values != previous)
    return {
        "cost_report_headers": len(headers), "report_end_years": dict(years), "literal_composite_flag_report_counts": dict(flags),
        "exact_ccn_and_period_gate_counts": dict(identity),
        "line13_subscript_groups": dict(subscript_counts), "literal_flag_and_cells": dict(scopes),
        "literal_y_header_matched_provider_ccns": sum("Y" in statuses for statuses in ccn_flags.values()),
        "literal_y_header_matched_provider_period_keys": len(y_periods),
        "literal_y_report_status_codes": dict(status_lit), "literal_y_group_quality_counts": dict(y_tiers),
        "shape_qualified_address_report_count": len(qualifying_reports),
        "shape_qualified_address_observation_count": y_tiers["complete_civic_shape"],
        "shape_qualified_address_distinct_ccn_count": len(providers),
        "shape_qualified_address_distinct_exact_tuples": len(all_civic),
        "shape_qualified_distinct_provider_and_tuple": len(provider_civic),
        "shape_qualified_address_comparison_to_printed_main": dict(main_relation),
        "literal_line11_distinct_part_for_line12_y_report_counts": dict(distinct_flags),
        "literal_line11_flag_by_line12_y_address_quality": {k: dict(v) for k, v in quality_by_distinct_flag.items()},
        "literal_line11_flag_by_line12_y_shape_comparison_to_printed_main": {k: dict(v) for k, v in main_by_distinct_flag.items()},
        "shape_qualified_observations_held_for_nonaffirmative_or_ambiguous_line11": y_tiers["complete_civic_shape"] - concordant_observations,
        "both_flags_y_and_civic_shape": {"reports": len(concordant_reports), "observations": concordant_observations,
                                        "distinct_ccns": len(concordant_ccns), "distinct_exact_tuples": len(concordant_tuples)},
        "y_provider_ccns_with_multiple_reports": sum(len(v) > 1 for v in report_histories.values()),
        "known_ccns_with_y_and_n_reports": sum({"Y", "N"} <= statuses for statuses in ccn_flags.values()),
        "repeated_y_provider_period_pairs": repeated_periods,
        "y_overlapping_period_pairs_with_different_nonempty_civic_sets": overlap_disagreement,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    try:
        pinned(args.archive)
        with zipfile.ZipFile(args.archive) as z:
            members = {m.filename: (m.file_size, f"{m.CRC:08x}") for m in z.infolist()}
            if len(z.infolist()) != len(MEMBERS) or members != MEMBERS:
                raise ValueError("SNF FY2025 ZIP member mismatch")
            headers = load_reports(member_rows(z, "SNF24_2025_rpt.csv"))
            fields, locations, n = load_fields(member_rows(z, "SNF24_2025_alpha.csv"))
        if (len(headers), n) != (REPORT_ROWS, ALPHA_ROWS):
            raise ValueError("unexpected pinned archive counts")
        result = summarize(headers, fields, locations)
    except (OSError, ValueError, csv.Error, zipfile.BadZipFile):
        parser.exit(2, "Composite address audit failed; no receipt produced.\n")
    result.update({
        "publisher_archive": {"catalog": CATALOG, "url": URL, "bytes": PIN[0], "sha256": PIN[1],
                              "last_modified_utc": "2026-10-05T23:54:28Z", "member_bytes_and_crc32": MEMBERS},
        "source_form": "CMS-2540-24", "form_cutover_min_report_end": FORM_CHANGE_END_DATE.isoformat(),
        "period_contemporaneous_instructions_sections_4901_30_4990_30_and_edit_1090S": "https://www.cms.gov/files/document/r1p249i.pdf",
        "revised_form_cutover_instructions_section_4900": "https://www.cms.gov/files/document/r3p249i.pdf",
        "regulatory_definition": "https://www.ecfr.gov/current/title-42/chapter-IV/subchapter-G/part-483/subpart-B/section-483.5",
        "worksheet_alpha_rows_screened": n, "worksheet": WORKSHEET,
        "coordinate_scope": {"ccn": "00300/00300", "report_period": "00900/00100–00200",
                             "literal_distinct_part_flag": "01100/00100", "literal_composite_flag": "01200/00100", "reported_component": "01300 and full subscripts, 00100–00600"},
        "limits": [
            "One status-selected historical archive; report dates are not publication, operation, certification, or location effective dates.",
            "Shape-only observation requires literal line 12 Y, exact header CCN and dates, and complete civic syntax. It is not concordant distinct-part evidence.",
            "The concordant reporting tier additionally requires one literal line 11 Y; N, missing and conflicting line 11 cannot be promoted.",
            "Discordant fields are publisher-reported responses, not a statutory or compliance determination.",
            "A shape-qualified tuple is not verified physical geography. Exact main-address repetition is not an additional site; differing strings can reflect formatting and establish no site count.",
            "Postal-only fields, missing/negative flags and duplicate/conflicting cells do not imply a site or absence of a site.",
            "No provider identity, address, site, control relationship, current certification, health outcome, inspection or asset determined or published.",
        ],
        "provider_addresses_or_rows_retained": 0, "numeric_or_rollup_members_opened": 0, "application_clearance": "pending",
    })
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
