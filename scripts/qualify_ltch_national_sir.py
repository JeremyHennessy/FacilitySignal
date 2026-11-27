"""Qualify only three FS-042 national infection ratios, local and aggregate-only.

No source download, provider file, Azure, clinical score output, comparison,
publication, or inferred facility relationship. This is semantic readiness,
not a change in the retained reuse review.
"""
import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re

from scripts.qualify_ltch_quality import CCN, RELEASE, SPECS, require

PIN = Path(__file__).resolve().parents[1] / "research/fs042_ltch_quality_qualification_20261127.json"
CATALOG = "https://data.cms.gov/provider-data/dataset/5zdx-ny2x"
DICTIONARY = "https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/long_term_care_hospital/LTCH_Data_Dictionary.pdf"
RELEASE_DATES = "https://www.cms.gov/medicare/quality/long-term-care-hospital/ltch-quality-public-reporting"
SIR_REFERENCE = "https://www.cdc.gov/healthcare-associated-infections/php/data/progress-report-faqs.html"
WINDOW = ("10/01/2024", "09/30/2025", "-")
FAMILIES = {"L_006_01": "CAUTI", "L_007_01": "CLABSI", "L_014_01": "CDI"}
NATIONAL = {f"{stem}_NATL_SIR": name for stem, name in FAMILIES.items()}
PROVIDER = {f"{stem}_SIR" for stem in FAMILIES}
DECIMAL = re.compile(r"[0-9]+(?:\.[0-9]+)?")


def sir_decimal(score):
    return Decimal(score) if isinstance(score, str) and DECIMAL.fullmatch(score) else None


def provider_score_state(code, score, footnote, window):
    """Synthetic guard: only classify a scoped scalar, never a comparison."""
    if code not in PROVIDER:
        return "outside_provider_sir_scalar"
    if window != WINDOW:
        return "window_unverified"
    numeric = sir_decimal(score)
    if score == "Not Available":
        return "unavailable"
    if score == "Not Applicable":
        return "not_applicable"
    if score in ("", "-", "--", "N/A"):
        return "missing_or_ambiguous_token"
    if numeric is None or footnote not in ("-", "6") or (footnote == "6" and numeric != 0):
        return "value_or_footnote_unverified"
    # CMS's footnote 6 can accompany an explicit zero or a masked score.
    # Only the literal numeric scalar above qualifies; never convert a note to 0.
    return "numeric_zero" if numeric == 0 else "numeric_nonzero"


def screen_national(stream, expected_rows):
    """Return aggregate counts after exact grain, token and period validation."""
    reader = csv.DictReader(stream, strict=True)
    require(reader.fieldnames == SPECS["national"][3], "LTCH national header drift")
    observed, all_codes = {}, set()
    for n, row in enumerate(reader, 1):
        require(n <= expected_rows and None not in row and None not in row.values(),
                "LTCH national width/count drift")
        code = row["Measure Code"]
        require(row[CCN] == "NATION" and code not in all_codes, "LTCH national grain/key mismatch")
        all_codes.add(code)
        if code not in NATIONAL:
            continue
        require((row["Start Date"], row["End Date"], row["Measure Date Range"]) == WINDOW,
                "LTCH national SIR window unverified")
        value = sir_decimal(row["Score"])
        require(value is not None and row["Footnote"] == "-", "LTCH national SIR score domain")
        observed[code] = value
    require(len(all_codes) == expected_rows and set(observed) == set(NATIONAL),
            "LTCH national SIR count/key mismatch")
    return {
        "national_input_rows": expected_rows,
        "sir_numeric_rows": len(observed),
        "sir_explicit_zero_rows": sum(x == 0 for x in observed.values()),
        "sir_scores_different_from_unity": sum(x != 1 for x in observed.values()),
        "other_national_rows_not_semantically_qualified": expected_rows - len(observed),
        "sir_measure_families": sorted(FAMILIES.values()),
        "observation_period_start": "2024-10-01", "observation_period_end": "2025-09-30",
    }


def qualify(path):
    prior = json.loads(PIN.read_text(encoding="utf-8"))["audit"]
    source = prior["sources"]["national"]
    publisher = source["publisher"]
    require(prior["source_id"] == "FS-042" and prior["reuse_review"] == "pending"
            and publisher["id"] == "5zdx-ny2x" and publisher["released"] == RELEASE
            and publisher["modified"] == "2026-08-12"
            and publisher["bytes"] == 1787 and source["input_rows"] == 27,
            "LTCH retained benchmark lineage drift")
    with path.open("rb") as src:
        payload = src.read(publisher["bytes"] + 1)
    require(len(payload) == publisher["bytes"] and hashlib.sha256(payload).hexdigest() == publisher["sha256"],
            "LTCH national bytes differ from retained receipt")
    result = screen_national(io.StringIO(payload.decode("utf-8-sig"), newline=""), source["input_rows"])
    return {
        "source_id": "FS-042", "release": RELEASE, "dataset_id": publisher["id"],
        "national_bytes": len(payload), "national_sha256": publisher["sha256"],
        "catalog": CATALOG, "dictionary_september_2026": DICTIONARY, "release_note": RELEASE_DATES,
        "dictionary_tables": [7, 8, 9],
        "sir_reference_explanation": SIR_REFERENCE, **result,
        "sir_unit": "unitless observed-to-predicted ratio",
        "boundary": "Published national LTCH SIR is distinct from the mathematical reference 1.0. "
                    "Do not derive provider comparison categories, baseline vintage, current safety, or an event rate.",
        "provider_observations_consumed": 0, "row_level_retained": 0,
        "public_promotion": False, "reuse_review": "pending",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("national_csv", type=Path)
    args = parser.parse_args()
    print(json.dumps(qualify(args.national_csv), indent=2, sort_keys=True))
