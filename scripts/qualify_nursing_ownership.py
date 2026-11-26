"""FS-039: qualify Care Compare nursing ownership, not PECOS all-owners.

CMS PDC y2hd-n93e; Table 13 of the Nursing Home data dictionary.
Only explicitly organizational rows enter a temporary SQLite projection.
No raw file, individual names, provider addresses, or row-level artifacts.
"""
import argparse
import csv
import hashlib
import json
import re
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import collect_cms as cms
from build_combined import require, sha, check_integrity

DATASET = "y2hd-n93e"
SOURCE = "FS-039"
HEADER = [
    "CMS Certification Number (CCN)", "Provider Name", "Provider Address",
    "City/Town", "State", "ZIP Code", "Role played by Owner or Manager in Facility",
    "Owner Type", "Owner Name", "Ownership Percentage", "Association Date",
    "Location", "Processing Date",
]
ROLES = frozenset(x.casefold() for x in (
    "5% or greater direct ownership interest", "DIRECT OWNERSHIP INTEREST",
    "5% or greater indirect ownership interest", "INDIRECT OWNERSHIP INTEREST",
    "5% OR GREATER MORTGAGE INTEREST", "5% OR GREATER SECURITY INTEREST",
    "MANAGING CONTROL - GOVERNING BODY", "CONTRACTED MANAGING EMPLOYEE",
    "W-2 MANAGING EMPLOYEE", "CORPORATE DIRECTOR", "CORPORATE OFFICER",
    "OPERATIONAL/MANAGERIAL CONTROL", "GENERAL PARTNERSHIP INTEREST",
    "LIMITED PARTNERSHIP INTEREST",
    "INDIVIDUAL IS AN OWNER, PARTNER OR TRUSTEE OF ANY ADP OF THE SNF",
    "TRUSTEE OF THE SNF", "ADP OF THE SNF",
))
MAX_BYTES = 150_000_000
MAX_ROWS = 500_000

def date_value(raw):
    raw = raw.strip()
    if not raw:
        return None, "blank"
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw):
        try:
            return date.fromisoformat(raw).isoformat(), "iso_date"
        except ValueError:
            pass
    return None, "date_review"

def percentage(raw):
    raw = raw.strip()
    if not raw:
        return None, "blank"
    # Do not interpret text tokens, missing values or undocumented scales.
    if not re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,8})?", raw):
        return None, "value_review"
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None, "value_review"
    if not 0 <= number <= 100:
        return None, "range_review"
    return raw, "numeric_literal"

def download(path):
    meta = cms.metadata(DATASET)
    expected = cms.count(DATASET)
    require(0 < expected <= MAX_ROWS, "source count bound")
    digest = hashlib.sha256()
    size = 0
    with cms.response(meta["url"]) as response, path.open("xb") as output:
        cms.allowed(response.geturl())
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            require(size <= MAX_BYTES, "source byte bound")
            digest.update(chunk)
            output.write(chunk)
    require(size > 0 and sha(path) == digest.hexdigest(), "source byte integrity")
    require(cms.metadata(DATASET) == meta and cms.count(DATASET) == expected,
            "source metadata/count changed")
    return {**meta, "sha256": digest.hexdigest(), "bytes": size}, expected

def project(stream, expected, db):
    reader = csv.DictReader(stream, strict=True)
    require(reader.fieldnames == HEADER, "FS039 header drift")
    db.execute("""CREATE TABLE organization_role(
        source_ordinal INTEGER PRIMARY KEY, ccn TEXT NOT NULL, state TEXT NOT NULL,
        owner_name TEXT NOT NULL, role TEXT NOT NULL, ownership_numeric_literal TEXT,
        ownership_value_state TEXT NOT NULL, association_date TEXT,
        association_date_state TEXT NOT NULL, processing_date TEXT NOT NULL
    )""")
    dispositions, roles, dates, percentages, processing = (Counter() for _ in range(5))
    total = 0
    for total, row in enumerate(reader, 1):
        require(total <= MAX_ROWS and None not in row and all(v is not None for v in row.values()),
                "FS039 row width or count bound")
        owner_type = row["Owner Type"].strip().casefold()
        if owner_type != "organization":
            dispositions["excluded_individual" if owner_type == "individual" else "excluded_unknown_owner_type"] += 1
            continue
        ccn = row[HEADER[0]].strip()
        state = row["State"].strip()
        name = row["Owner Name"].strip()
        role = row[HEADER[6]].strip().casefold()
        if not re.fullmatch(r"[A-Z0-9]{6}", ccn) or not re.fullmatch(r"[A-Z]{2}", state):
            dispositions["excluded_identifier_review"] += 1
            continue
        if not name or len(name) > 300 or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in name):
            dispositions["excluded_name_review"] += 1
            continue
        if role not in ROLES:
            dispositions["excluded_role_review"] += 1
            continue
        proc, ps = date_value(row["Processing Date"])
        if ps != "iso_date":
            dispositions["excluded_processing_date_review"] += 1
            continue
        assoc, ds = date_value(row["Association Date"])
        if assoc is not None and assoc > proc:
            assoc, ds = None, "after_processing_review"
        pct, vs = percentage(row["Ownership Percentage"])
        db.execute("INSERT INTO organization_role VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (total, ccn, state, name, role, pct, vs, assoc, ds, proc))
        dispositions["stored_organization"] += 1
        roles[role] += 1
        dates[ds] += 1
        percentages[vs] += 1
        processing[proc] += 1
    stored = db.execute("SELECT count(*) FROM organization_role").fetchone()[0]
    require(total == expected == sum(dispositions.values()), "FS039 input reconciliation")
    require(stored == dispositions["stored_organization"] > 0, "FS039 empty or mismatched projection")
    require(all(sum(c.values()) == stored for c in (roles, dates, percentages, processing)),
            "FS039 projected field reconciliation")
    db.execute("CREATE INDEX organization_role_ccn ON organization_role(ccn,state)")
    db.commit()
    check_integrity(db)
    distinct = db.execute("SELECT count(DISTINCT ccn) FROM organization_role").fetchone()[0]
    distinct_tuple = db.execute("""SELECT count(*) FROM (
        SELECT DISTINCT ccn,state,owner_name,role,ownership_numeric_literal,
        ownership_value_state,association_date,association_date_state,processing_date
        FROM organization_role)""").fetchone()[0]
    return {
        "source_id": SOURCE, "dataset_id": DATASET, "source_columns": len(HEADER),
        "input_rows": total, "stored_organization_rows": stored, "dispositions": dict(dispositions),
        "source_reported_roles": dict(roles), "association_date_states": dict(dates),
        "ownership_value_states": dict(percentages), "processing_date_counts": dict(processing),
        "distinct_source_ccns": distinct, "repeated_projected_tuple_rows": stored - distinct_tuple,
        "individual_rows_retained": 0, "public_rows_retained": 0, "azure_writes": 0,
        "reuse_review": "pending",
        "limits": "Temporary organizational role observations, not canonical owners, physical property owners, verified management contracts, current relationships or procurement opportunities. Repeated tuples preserved. Percentage semantics not qualified beyond numeric literal. No raw or row-level artifacts.",
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    require(not args.audit.exists(), "new audit path required")
    with tempfile.TemporaryDirectory(prefix="fs039-") as tmp:
        root = Path(tmp)
        raw = root / "ownership.csv"
        meta, expected = download(raw)
        with raw.open(encoding="utf-8-sig", newline="") as stream, closing(sqlite3.connect(root / "projection.sqlite3")) as db:
            result = project(stream, expected, db)
        require(sha(raw) == meta["sha256"], "source changed locally")
    result.update(publisher=meta, retrieved_at=datetime.now(timezone.utc).isoformat())
    with args.audit.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print("FS039_AGGREGATE_AUDIT", json.dumps(result, sort_keys=True), flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never echo source rows, exception values, or remote response content.
        print("FS039_QUALIFICATION_FAILED", type(error).__name__, flush=True)
        raise SystemExit(1) from None
