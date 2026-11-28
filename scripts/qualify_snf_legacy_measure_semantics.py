"""Qualify the eight pinned SNF cost-report measures without re-reading private data.

The 2022 dictionary describes the legacy 2540-10 form only. New 2540-24
periods require a separate reviewed coordinate map. No monetary scaling,
provider-level attribution, publication or purchasing inference is authorized.
"""
import hashlib
import json
from datetime import date
from pathlib import Path

PIN = "7dba1fe969c1e0b7d9e82345175dd8e65c4bc3a7"
SOURCE = Path(__file__).resolve().parents[1] / "research/hcris_direct_measure_crosswalk_20261126.json"
DICTIONARY = "https://data.cms.gov/sites/default/files/2023-12/Skilled%20Nursing%20Facility%20Cost%20Report%20Data%20Dictionary_508.pdf"
TRANSITION = "https://www.cms.gov/files/document/r1p249i.pdf"
SUNSET = "https://www.cms.gov/files/document/R11P241i.pdf"
REVISION = "https://www.cms.gov/files/document/r2p249i.pdf"
# Revised November 27, 2024 transmittal supersedes its stale landing-page summary.
BOUNDARY = date(2025, 9, 30)
# Coordinate, dictionary page (one-based), reporting grain, interpretation.
MEASURES = {
    "Contract Labor": (("S300002", "01400", "00300"), 4, "period_flow", "Contracted direct-care and defined senior-management services; not all vendor or facilities-service expenditure."),
    "Number of Beds": (("S300001", "00800", "00100"), 1, "period_end_count", "Beds available at report end across the reported complex; not current licensed or staffed beds."),
    "Overhead Non-Salary Costs": (("A000000", "10000", "00200"), 4, "period_flow", "Other non-salary accounting expenses; not a facilities-maintenance-only budget."),
    "Total Bed Days Available": (("S300001", "00800", "00200"), 1, "period_capacity", "Capacity integrated over the reporting period; not end-period beds multiplied by a fixed 365."),
    "Total Charges": (("C000000", "10000", "00200"), 4, "period_flow", "Gross patient charges with dictionary-specific inclusions and exclusions; not payments or collected revenue."),
    "Total Costs": (("C000000", "10000", "00100"), 4, "period_flow", "Reported SNF costs; not a property-specific budget."),
    "Total Days Total": (("S300001", "00800", "00700"), 1, "period_mixed_utilization", "Inpatient days or visits as applicable, combined across programs/components; not automatically an occupancy numerator."),
    "Total Salaries From Worksheet A": (("A000000", "10000", "00100"), 4, "period_flow", "Salary expense from accounting records; not adjusted wage-index salaries or contractor spend."),
}


def form_gate(form, begin, end):
    """Require explicit form plus valid period; apply revised period-end boundary."""
    if not isinstance(begin, date) or not isinstance(end, date) or end < begin:
        return "unresolved_period"
    if form == "2540-10":
        return "legacy_map_candidate" if end < BOUNDARY else "form_period_conflict"
    if form == "2540-24":
        return "new_form_mapping_required" if end >= BOUNDARY else "form_period_conflict"
    return "unresolved_form"


def qualify(raw):
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if blob != PIN:
        raise ValueError("crosswalk blob mismatch")
    source = json.loads(raw)["forms"]["snf"]
    cohort = source["report_key_intersection"]
    if set(source["measures"]) != set(MEASURES):
        raise ValueError("unexpected measure domain")
    measures = {}
    for name, (coordinate, page, grain, meaning) in MEASURES.items():
        evidence = source["measures"][name]
        comparisons = evidence["comparisons"]
        if (tuple(evidence["coordinate"]) != coordinate
                or evidence["archive_duplicate_coordinate_report_keys"] != 0
                or set(comparisons) != {"equal_decimal", "puf_missing_archive_absent"}
                or sum(comparisons.values()) != cohort):
            raise ValueError("unreconciled measure evidence")
        measures[name] = {
            "coordinate": coordinate, "dictionary_page": page,
            "reporting_grain": grain, "interpretation": meaning,
            "unit_candidate": evidence["unit_candidate"],
            "matched_report_present": comparisons["equal_decimal"],
            "matched_report_missing": comparisons["puf_missing_archive_absent"],
            "monetary_scale_qualified": False,
            "facility_attribution": False,
            "publication_clearance": False,
        }
    return {
        "source_git_blob": blob, "dictionary_url": DICTIONARY,
        "dictionary_date": "2022-12-16", "form_transition_url": TRANSITION,
        "legacy_form": "2540-10", "new_form_effective_end": BOUNDARY.isoformat(),
        "legacy_sunset_url": SUNSET, "subsequent_revision_url": REVISION,
        "transition_note": "Revised November 27, 2024 PDF supersedes original October landing-page summary; subsequent April 2025 electronic specification dates are separate.",
        "matched_reports": cohort, "measures": measures,
        "new_form_coordinates_qualified": 0,
        "row_values_read_or_retained": 0,
        "occupancy_ratio_qualified": False,
        "application_clearance": "pending",
    }


if __name__ == "__main__":
    print(json.dumps(qualify(SOURCE.read_bytes()), sort_keys=True, indent=2))
