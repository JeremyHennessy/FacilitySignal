"""Compare exact November PECOS REH IDs with historical OP-36, offline and aggregate only."""

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from scripts import qualify_reh_op36 as op36

CATALOG = "https://data.cms.gov/data-api/v1/dataset-resources/f6f6505c-e8b0-4d57-b258-e2b94133aaf2"
ENROLL_URL = "https://data.cms.gov/sites/default/files/2026-11/68a679e0-ec3c-4c6f-98cf-566084547755/Hospital_Enrollments_2026.11.12.csv"
DICTIONARY_URL = "https://data.cms.gov/sites/default/files/2026-11/Hospital_Enrollments_Data_Dictionary.pdf"
ENROLL_PIN = (3089060, "d7ce302f73195b3ce6018291f3ee82af0ec026e51a3145bb9af41be8fbaa194e")
DICTIONARY_PIN = (250776, "3f98051204fa840e747dd6e90b51b2c53335f8dbcb1327d01c5858624b3aedea")
ENROLL_ROWS = 9120
REH_TYPE = "00-24"
REH_LABEL = "PART A PROVIDER - RURAL EMERGENCY HOSPITAL (REH)"
OTHER_TYPES = {"00-09": "PART A PROVIDER - HOSPITAL", "00-85": "PART A PROVIDER - CRITICAL ACCESS HOSPITAL"}
FIELDS = ("ENROLLMENT ID", "ASSOCIATE ID", "CCN", "ENROLLMENT STATE", "STATE",
          "PROVIDER TYPE CODE", "PROVIDER TYPE TEXT", "REH CONVERSION FLAG", "REH CONVERSION DATE")
CUTOFF = date(2024, 12, 31)
SNAPSHOT = date(2026, 11, 12)
CCN = re.compile(r"[0-9]{6}")
STATE = re.compile(r"[A-Z]{2}")
BUCKETS = ("on_or_before_period_end", "after_period_end", "not_reported")


def read_enrollment(path):
    size, digest = ENROLL_PIN
    with path.open("rb") as f:
        raw = f.read(size + 1)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("PECOS source pin mismatch")
    return raw


def enrollment_records(raw):
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True))
    if len(rows) != ENROLL_ROWS + 1:
        raise ValueError("unexpected enrollment row count")
    header = rows[0]
    if len(header) != 39 or len(set(header)) != len(header) or not set(FIELDS) <= set(header):
        raise ValueError("unexpected enrollment columns")
    positions = {col: header.index(col) for col in FIELDS}
    for row in rows[1:]:
        if len(row) != len(header):
            raise ValueError("unexpected enrollment row width")
        yield {key: row[index] for key, index in positions.items()}


def date_bucket(text):
    if not text:
        return "not_reported"
    if not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", text):
        raise ValueError("invalid conversion date form")
    actual = datetime.strptime(text, "%m/%d/%Y").date()
    if actual > SNAPSHOT:
        raise ValueError("conversion date after snapshot")
    return "on_or_before_period_end" if actual <= CUTOFF else "after_period_end"


def typed_index(rows):
    all_ids, ids, associates, other = set(), set(), set(), set()
    typed = {}
    groups = Counter()
    for r in rows:
        code, label, ccn = (r[key] for key in ("PROVIDER TYPE CODE", "PROVIDER TYPE TEXT", "CCN"))
        eid = r["ENROLLMENT ID"]
        if not re.fullmatch(r"[A-Z0-9]{15}", eid) or eid in all_ids:
            raise ValueError("invalid or duplicate enrollment ID")
        all_ids.add(eid)
        groups[code] += 1
        if code != REH_TYPE:
            if OTHER_TYPES.get(code) != label:
                raise ValueError("unexpected code/text pair")
            if CCN.fullmatch(ccn):
                other.add(ccn)
            continue
        if label != REH_LABEL:
            raise ValueError("REH code/text conflict")
        pac, enrollment, practice = (r[key] for key in ("ASSOCIATE ID", "ENROLLMENT STATE", "STATE"))
        if (not re.fullmatch(r"[0-9]{10}", pac)
                or not CCN.fullmatch(ccn) or ccn in typed or not STATE.fullmatch(enrollment) or not STATE.fullmatch(practice)):
            raise ValueError("invalid or duplicate typed record identity")
        if r["REH CONVERSION FLAG"] != "Y":
            raise ValueError("unexpected conversion flag for pinned source edition")
        ids.add(eid)
        associates.add(pac)
        typed[ccn] = (enrollment, practice, date_bucket(r["REH CONVERSION DATE"]))
    return typed, other, len(ids), len(associates), dict(groups)


def compare(enrollments, measure):
    typed, other, ids, pac, provider_types = typed_index(enrollments)
    if set(typed) & other:
        raise ValueError("ambiguous exact CCN across current specialty codes")
    op36.qualify_provider(measure)  # confirms historical scope and unique exact measure IDs; no values retained
    history = {r["Facility ID"]: r["State"] for r in measure}
    both = typed.keys() & history.keys()
    if any(typed[ccn][:2] != (history[ccn], history[ccn]) for ccn in both):
        raise ValueError("exact CCN with conflicting state in matched scope")

    def buckets(keys):
        counts = Counter(typed[key][2] for key in keys)
        return {name: counts[name] for name in BUCKETS}

    enrollment_only = typed.keys() - history.keys()
    return {
        "pecos_snapshot_file_date": SNAPSHOT.isoformat(),
        "pecos_date_basis": "dated CMS publisher filename, not an enrollment effective date",
        "op36_performance_period": ["2024-01-01", CUTOFF.isoformat()],
        "historical_op36_catalog_release": "2026-11-12",
        "record_scope": "approved Medicare hospital enrollment applications in the pinned November PECOS export",
        "provider_type_code": REH_TYPE,
        "all_enrollment_rows": sum(provider_types.values()),
        "enrollment_counts_by_type_code": provider_types,
        "typed_enrollment_rows": len(typed),
        "typed_distinct_enrollment_ids": ids,
        "typed_distinct_pac_ids": pac,
        "typed_distinct_exact_ccns": len(typed),
        "op36_distinct_exact_ccns": len(history),
        "both_sources_exact_ccn_both_states_agree": len(both),
        "op36_only": len(history.keys() - typed.keys()),
        "typed_pecos_only": len(enrollment_only),
        "later_pecos_reported_conversion_date_by_match_scope": {
            "exact_matched": buckets(both), "pecos_only": buckets(enrollment_only),
        },
        "limits": [
            "Different identifiers and grains: enrollments, enrolling PECOS associates, exact CCNs, and historical quality-measure observations.",
            "Classification only uses explicit PECOS provider type code, corroborated by publisher label; never CCN suffix or historical former-provider field.",
            "Exact same CCN and state across releases does not establish identical entity, site, REH status at the earlier date or reporting eligibility.",
            "Later PECOS reported conversion date is not independently adjudicated historical certification or operational evidence.",
            "No operating census, current service or historic/program denominator inferred. This does not explain OP-36 provider and national count differences.",
        ],
        "application_clearance": "pending",
        "provider_rows_retained": 0,
        "provider_identifiers_or_values_retained": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enrollment", type=Path, required=True)
    parser.add_argument("--op36-provider", type=Path, required=True)
    a = parser.parse_args()
    try:
        source = enrollment_records(read_enrollment(a.enrollment))
        history = op36.records(op36.load_pinned(a.op36_provider, "provider"), op36.PROVIDER_COLUMNS, 49)
        report = compare(source, history)
    except (OSError, ValueError, csv.Error):
        parser.exit(2, "PECOS REH input verification failed; no receipt produced.\n")
    cid, size, digest, op_path = op36.PINS["provider"]
    report["sources"] = {
        "enrollment": {"catalog_resource": CATALOG, "download": ENROLL_URL, "bytes": ENROLL_PIN[0], "sha256": ENROLL_PIN[1]},
        "enrollment_dictionary_reviewed": {"download": DICTIONARY_URL, "bytes": DICTIONARY_PIN[0], "sha256": DICTIONARY_PIN[1]},
        "op36_provider": {"catalog": op36.CATALOG + cid, "download": op36.RESOURCES + op_path, "bytes": size, "sha256": digest},
        "ccn_suffix_overlap": ["https://www.cms.gov/files/document/r12369cp.pdf",
                               "https://www.cms.gov/regulations-and-guidance/guidance/manuals/downloads/som107c02.pdf"],
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
