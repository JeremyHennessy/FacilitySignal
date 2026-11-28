"""Offline SNF24 FY2025 Worksheet A coverage gate. Run with python -m scripts.qualify_snf24_cost_coverage --archive PATH.
Only an already authorized local pinned copy is accepted; no network, writes or monetary values in output.
"""
import argparse
import csv
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts import qualify_snf_composite_addresses as source

# CMS PRM chapter 49 sections 4902.10, 4990.20 Table 2, 4990.60.10 edit 1080.
# Capital-related expenses are not purchases. Base lines only, never silently sum subscripts.
CENTERS = {
    "00100": "building_fixture_costs",
    "00200": "movable_equipment_costs",
    "00500": "plant_maintenance_repairs",
    "00600": "laundry_linen",
    "00700": "housekeeping",
    "00800": "nutrition_services",
}
COLUMNS = {"00100": "employee_wages", "00200": "contract_labor",
           "00300": "labor_subtotal", "00400": "nonlabor_costs", "00500": "unadjusted_subtotal"}
CAPITAL = {"00100", "00200"}
REV3 = date(2026, 6, 30)
REVISIONS = ("pre_rev3", "rev3", "unresolved")
DOCS = {
    "initial": "https://www.cms.gov/files/document/r1p249i.pdf",
    "revision2": "https://www.cms.gov/files/document/r2p249i.pdf",
    "revision3": "https://www.cms.gov/files/document/r3p249i.pdf",
}


def columns(line):
    return ("00400", "00500") if line in CAPITAL else tuple(COLUMNS)


def load_identity(rows):
    data = defaultdict(lambda: defaultdict(list))
    n = 0
    for n, row in enumerate(rows, 1):
        if len(row) != 5:
            raise ValueError("unexpected alpha width")
        key, sheet, line, col, val = row
        if sheet == source.WORKSHEET:
            field = source.SCALAR.get((line, col))
            if field in ("ccn", "begin", "end"):
                data[key][field].append(val)
    return data, n


def value(raw):
    # CMS Ch. 49 §4900.10: a positive number must not have a leading plus.
    # No inferred scale, coercion of blanks, exponent, NaN, or rounding.
    if not re.fullmatch(r"-?[0-9]{1,18}(?:\.[0-9]{1,8})?", raw):
        return None
    return Decimal(raw)


def audit(headers, identities, rows):
    if identities.keys() - headers.keys():
        raise ValueError("unlinked identity cells")
    cohorts = {}
    for key, hdr in headers.items():
        bounds, _ = source.report_bounds(hdr, identities.get(key, {}))
        cohorts[key] = ("rev3" if bounds[1] >= REV3 else "pre_rev3") if bounds else "unresolved"
    cells = defaultdict(list)
    held = set()
    scan = Counter()
    for row in rows:
        scan["input_rows"] += 1
        if len(row) != 5:
            raise ValueError("unexpected numeric width")
        key, sheet, line, col, raw = row
        if key not in headers:
            scan["orphan_numeric_rows"] += 1
            continue
        if sheet != "A000000":
            continue
        scan["worksheet_a_rows"] += 1
        if not re.fullmatch(r"[0-9]{5}", line) or not re.fullmatch(r"[0-9]{5}", col):
            raise ValueError("unexpected Worksheet A coordinate")
        base = line[:3] + "00"
        if base not in CENTERS:
            continue
        if line != base:
            held.add((key, base))
            scan["subscript_rows_held"] += 1
            continue
        if col not in columns(base):
            scan["other_base_column_rows"] += 1
            continue
        scan["target_base_rows"] += 1
        cells[key, base, col].append(raw)
    if scan["orphan_numeric_rows"]:
        raise ValueError("orphan numeric rows")
    counts = {rev: {CENTERS[line]: {COLUMNS[col]: Counter() for col in columns(line)}
                   for line in CENTERS} for rev in REVISIONS}
    equations = {rev: {CENTERS[line]: {name: Counter() for name in ("labor", "subtotal")}
                       for line in CENTERS if line not in CAPITAL} for rev in REVISIONS}
    for key, rev in cohorts.items():
        for line, center in CENTERS.items():
            valid = {}
            for col in columns(line):
                vals = cells.get((key, line, col), ())
                if rev == "unresolved":
                    status = "identity_or_period_held"
                elif (key, line) in held:
                    status = "subscript_held"
                elif len(vals) > 1:
                    status = "duplicate_held"
                elif not vals:
                    status = "absent"
                elif (num := value(vals[0])) is None:
                    status = "blank_or_invalid_held"
                else:
                    valid[col] = num
                    status = "zero" if num == 0 else "negative" if num < 0 else "positive"
                counts[rev][center][COLUMNS[col]][status] += 1
            if line not in CAPITAL:
                for name, (a, b, c) in {"labor": ("00100","00200","00300"),
                                         "subtotal": ("00300","00400","00500")}.items():
                    status = ("exact" if valid[a] + valid[b] == valid[c] else "unequal") if all(x in valid for x in (a,b,c)) else "incomplete"
                    equations[rev][center][name][status] += 1
    cohort_counts = Counter(cohorts.values())
    if any(sum(c.values()) != cohort_counts[rev] for rev, groups in counts.items() for g in groups.values() for c in g.values()):
        raise ValueError("coverage accounting mismatch")
    return {"report_counts": dict(cohort_counts), "scan": dict(scan), "coordinate_counts": counts,
            "equation_counts": equations, "form": "2540-24",
            "revision3_effective_report_end": REV3.isoformat(), "documentation": DOCS,
            "worksheet": "A000000", "coordinate_count": sum(len(columns(x)) for x in CENTERS),
            "scope": "Base-row historical report observations, not category totals, payments, purchases, vendors or current sites.",
            "column2_revision": {"pre_rev3": "Contract wages and wage-related amounts; original instructions reference 1099 recipients.",
                                 "rev3": "Clarified to include labor supplied by companies as well as 1099 recipients."},
            "monetary_scale_qualified": False, "facility_attribution": False,
            "publication_clearance": False, "retained_row_count": 0}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", required=True, type=Path)
    args = p.parse_args()
    try:
        source.pinned(args.archive)
        with zipfile.ZipFile(args.archive) as z:
            members = {m.filename: (m.file_size, f"{m.CRC:08x}") for m in z.infolist()}
            if len(z.infolist()) != len(source.MEMBERS) or members != source.MEMBERS:
                raise ValueError("member pin mismatch")
            hdr = source.load_reports(source.member_rows(z, "SNF24_2025_rpt.csv"))
            identities, n = load_identity(source.member_rows(z, "SNF24_2025_alpha.csv"))
            if (len(hdr), n) != (source.REPORT_ROWS, source.ALPHA_ROWS):
                raise ValueError("archive count mismatch")
            result = audit(hdr, identities, source.member_rows(z, "SNF24_2025_nmrc.csv"))
        result["archive_sha256"] = source.PIN[1]
        result["alpha_rows_screened"] = n
    except (ValueError, OSError, csv.Error, zipfile.BadZipFile):
        p.exit(2, "SNF24 cost coverage audit failed; no receipt produced.\n")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
