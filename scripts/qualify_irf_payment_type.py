"""Compare exact historical IRF payment classifications, retaining aggregates only."""

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

from scripts import qualify_irf_hcris_relationship as hcris

PSF_SIZE = 2789406
PSF_HASH = "e87846f28d3f96704f75c37ba4f4c4577ecd809bb3b930024752ba8d237a293f"
PSF_URL = "https://www.cms.gov/medicare/medicare-fee-for-service-payment/prospmedicarefeesvcpmtgen/downloads/irf-psf.zip"
PSF_MEMBER = "IPSF_IRF_2025-10-01.csv"
PSF_INFO = (26442913, "34d7b3bd")
PSF_ROWS = 90916
EDITION = date(2025, 10, 1)
CHECKPOINTS = (date(2024, 9, 30), EDITION)
COLUMNS = ("providerCcn", "effectiveDate", "terminationDate", "intermediaryNumber", "providerType", "waiverIndicator")
STRONG = "type5_and_report_companions_corroborated"


def parse_date(value, termination=False):
    if termination and value in ("", "00000000"):
        return None
    if re.fullmatch(r"[0-9]{8}", value):
        try:
            return datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            pass
    return False


def pinned_psf(path):
    with path.open("rb") as f:
        if path.stat().st_size != PSF_SIZE or hashlib.file_digest(f, "sha256").hexdigest() != PSF_HASH:
            raise ValueError("IRF PSF edition mismatch")


def psf_index(path, scope):
    pinned_psf(path)
    index = defaultdict(list)
    with zipfile.ZipFile(path) as z:
        member = z.getinfo(PSF_MEMBER)
        if (member.file_size, f"{member.CRC:08x}") != PSF_INFO:
            raise ValueError("IRF PSF member mismatch")
        with z.open(member) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, strict=True)
            fields = next(reader, [])
            if len(fields) != 68 or len(set(fields)) != 68 or not set(COLUMNS) <= set(fields):
                raise ValueError("IRF PSF schema mismatch")
            positions = [fields.index(k) for k in COLUMNS]
            n = 0
            for n, row in enumerate(reader, 1):
                if len(row) != len(fields):
                    raise ValueError("IRF PSF row width mismatch")
                ccn = row[positions[0]]
                if ccn not in scope:
                    continue
                _, start, end, mac, typ, waiver = (row[i] for i in positions)
                if not re.fullmatch(r"[0-9]{5}", mac):
                    raise ValueError("malformed exact-match MAC identifier")
                if not re.fullmatch(r"[0-9]{2}", typ) or waiver not in ("N", "Y", "", " "):
                    raise ValueError("unexpected scoped classification or waiver literal")
                index[ccn].append((mac, parse_date(start), parse_date(end, termination=True), typ, waiver))
    if n != PSF_ROWS:
        raise ValueError("IRF PSF source count mismatch")
    return index


def period_result(rows, day):
    """Reconstruct one latest date per MAC; do not select from overlaps or stale versions."""
    if not rows:
        return "no_exact_ccn"
    by_mac = defaultdict(list)
    for mac, start, end, typ, waiver in rows:
        if start is False or start is None:
            return "unresolved_effective_date"
        if start <= day:
            by_mac[mac].append((start, end, typ, waiver))
    if not by_mac:
        return "only_future_records"
    active = []
    flags = set()
    for choices in by_mac.values():
        latest = max(v[0] for v in choices)
        top = [v for v in choices if v[0] == latest]
        if len(top) != 1:
            flags.add("ambiguous_same_mac_latest")
            continue
        start, end, typ, waiver = top[0]
        if end is False or (end is not None and end < start):
            flags.add("invalid_latest_interval")
            continue
        if end is None or day <= end:
            active.append((typ, waiver.strip() or "blank"))
    if flags:
        return "+".join(sorted(flags))
    if len(active) > 1:
        return "multiple_unended_macs_" + ("same_type" if len({x[0] for x in active}) == 1 else "conflicting_types")
    if not active:
        return "no_unended_mac"
    typ, waiver = active[0]
    return "type_" + typ + "_waiver_" + waiver


def cohort_summary(scope, psf):
    return {
        "requested_ccns": len(scope),
        "any_exact_psf_ccn": sum(ccn in psf for ccn in scope),
        "any_literal_type50_with_effective_date_by_extract": sum(
            any(typ == "50" and start and start <= EDITION for _, start, _, typ, _ in psf.get(ccn, ())) for ccn in scope),
        "inverted_source_intervals_across_all_versions": sum(
            bool(start and end and end < start) for ccn in scope for _, start, end, _, _ in psf.get(ccn, ())),
        "retrospective_checkpoint_counts": {day.isoformat(): dict(Counter(period_result(psf.get(c, ()), day) for c in scope))
                                             for day in CHECKPOINTS},
    }


def exact_cohorts(path):
    hcris.pinned(path)
    source = hcris.directory_cohorts(hcris.directory.load("rehabilitation"),
                                    hcris.directory.load("hospital") + hcris.directory.load("long-term-hospital"))
    candidates = source["all_literal_identifier_candidates"]
    with zipfile.ZipFile(path) as z:
        headers = hcris.load_reports(z)
        alpha, _ = hcris.load_alpha(z)
        types = hcris.load_numeric_type(z)
    pairs, strong, dated = set(), set(), []
    for rid, header in headers.items():
        _, pair = hcris.classify(header, alpha.get(rid, {}), types.get(rid, ()))
        if pair is None:
            continue
        parent, unit, _, end, _, _, strength = pair
        if candidates.get(unit) != parent:
            continue
        pairs.add(unit)
        dated.append((unit, end, strength))
        if strength == STRONG:
            strong.add(unit)
    missing = candidates.keys() - pairs
    if (len(candidates), len(pairs), len(strong), len(missing)) != (810, 752, 751, 58):
        raise ValueError("existing HCRIS aggregate cohort pin mismatch")
    return {"all_candidates": candidates.keys(), "literal_hcris_pair": pairs,
            "companion_corroborated_hcris_pair": strong, "no_literal_hcris_pair": missing}, dated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--psf", type=Path, required=True)
    parser.add_argument("--hcris", type=Path, required=True)
    args = parser.parse_args()
    try:
        cohorts, dated = exact_cohorts(args.hcris)
        psf = psf_index(args.psf, cohorts["all_candidates"])
    except (OSError, ValueError, csv.Error, zipfile.BadZipFile):
        parser.exit(2, "Historical IRF payment audit failed; no receipt produced.\n")
    ends = {mode: dict(Counter(period_result(psf.get(unit, ()), end)
                              for unit, end, strength in dated if mode == "all_literal" or strength == STRONG))
            for mode in ("all_literal", "companion_corroborated")}
    report = {
        "psf": {"url": PSF_URL, "bytes": PSF_SIZE, "sha256": PSF_HASH, "member": PSF_MEMBER,
                "member_uncompressed_bytes": PSF_INFO[0], "member_crc32": PSF_INFO[1], "member_rows": PSF_ROWS,
                "member_file_edition": EDITION.isoformat(), "http_last_modified_utc": "2025-11-13T16:32:49Z",
                "projected_fields": COLUMNS},
        "psf_reference": "https://www.cms.gov/files/document/r12615cp.pdf",
        "satellite_scope_reference": "https://www.ecfr.gov/current/title-42/chapter-IV/subchapter-B/part-412/subpart-B/section-412.25",
        "hcris_lineage": {"receipt": "research/irf_hcris_report_relationship_20261128.json", "archive_sha256": hcris.ZIP_HASH},
        "cohorts": {name: cohort_summary(scope, psf) for name, scope in cohorts.items()},
        "at_hcris_report_end_reconstructed_from_october_2025_extract": ends,
        "at_hcris_report_end_assessment_rows": {mode: sum(outcomes.values()) for mode, outcomes in ends.items()},
        "limits": [
            "Exact full CCN only, preserving letters and leading zeros; links and sites not inferred.",
            "Type 04 denotes rehabilitation facility; type 50 denotes rehabilitation distinct part. Literal waiver is separate.",
            "Each checkpoint uses latest effective record per MAC; the termination date is inclusive as the last specified MAC service date, not closure. Superseded rows are not revived.",
            "Multiple unended MACs and malformed latest intervals are held; same-day latest-version ties are not broken arbitrarily.",
            "This is retrospective effective-date reconstruction from an October 2025 extract, not information known at the checked time, contemporaneous proof, or observed payments.",
            "Payment classification does not supply parent identity, current certification, shared premises, satellite status, ownership or current operation.",
        ],
        "application_clearance": "pending", "provider_rows_identifiers_or_values_retained": 0,
    }
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
