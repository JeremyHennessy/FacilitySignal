"""Archive the exact qualified FS-039 release, only in private Azure storage.

Reuse the original projection unchanged. Retain bounded date-like and percentage-
like source text for explicitly organizational rows only; do not infer date
ordering, monetary scale, owner identity, or ownership relationships.
"""
import argparse
import csv
import json
import os
import re
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path

import azure_national_archive as a
from build_combined import require, sha, check_integrity
from scripts import azure_source_archive as storemod
from scripts import qualify_nursing_ownership as q

KEY = "cms-nursing-ownership-organizations"
PIN = "7a103a44530a2cc8756d9a9d3cfa01819ad74ef67f59d7eefa798d5573518045"
RELEASE = "2026-10-28"
ROWS = 252468
STORED = 71270
QUALIFICATION_RUN = 45900035551
PERCENT_ROLES = {"5% or greater direct ownership interest", "5% or greater indirect ownership interest"}
MISSING = {"", "n/a", "na", "not applicable", "not available", "-", "--", "unknown", "null"}

def source_literal(raw, field):
    s = raw.strip()
    if s.casefold() in MISSING:
        return None, "blank" if not s else "missing_token"
    if field == "date":
        patterns = (("iso_shape", r"[0-9]{4}-[0-9]{2}-[0-9]{2}"),
                    ("slash_date_shape", r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}"),
                    ("compact_date_shape", r"[0-9]{8}"),
                    ("dash_date_shape", r"[0-9]{1,2}-[0-9]{1,2}-[0-9]{4}"))
    elif field == "percentage":
        patterns = (("decimal_shape", r"[0-9]{1,3}(?:\.[0-9]{1,8})?"),
                    ("percent_marked_shape", r"[0-9]{1,3}(?:\.[0-9]{1,8})? *%"))
    else:
        raise ValueError("unsupported source field")
    for kind, pattern in patterns:
        if re.fullmatch(pattern, s):
            return s, kind
    return None, "other_text_review"

def verify_projection(summary):
    require(summary["input_rows"] == ROWS and summary["stored_organization_rows"] == STORED,
            "FS039 qualified release count drift")
    require(summary["dispositions"] == {"excluded_individual": 180548,
                                       "excluded_unknown_owner_type": 650,
                                       "stored_organization": STORED},
            "FS039 qualified exclusion drift")
    require(summary["distinct_source_ccns"] == 12052 and summary["repeated_projected_tuple_rows"] == 0
            and summary["individual_rows_retained"] == summary["public_rows_retained"] == 0,
            "FS039 qualified projection drift")

def retain_literals(stream, db, expected):
    reader = csv.DictReader(stream, strict=True)
    require(reader.fieldnames == q.HEADER, "literal source header drift")
    db.execute("CREATE TABLE source_field_literals(source_ordinal INTEGER PRIMARY KEY REFERENCES organization_role(source_ordinal), association_text TEXT, association_format TEXT NOT NULL, percentage_text TEXT, percentage_format TEXT NOT NULL)")
    ordinals = {row[0] for row in db.execute("SELECT source_ordinal FROM organization_role")}
    date_counts, percent_counts = Counter(), Counter()
    total = 0
    for total, row in enumerate(reader, 1):
        require(None not in row and all(v is not None for v in row.values()), "literal source row width")
        if total not in ordinals:
            continue
        require(row["Owner Type"].strip().casefold() == "organization", "literal owner scope")
        d, ds = source_literal(row["Association Date"], "date")
        p, ps = source_literal(row["Ownership Percentage"], "percentage")
        if row[q.HEADER[6]].strip().casefold() not in PERCENT_ROLES:
            p, ps = None, "outside_dictionary_role_" + ("missing" if ps in {"blank","missing_token"} else "review")
        db.execute("INSERT INTO source_field_literals VALUES(?,?,?,?,?)", (total,d,ds,p,ps))
        date_counts[ds] += 1
        percent_counts[ps] += 1
    n = len(ordinals)
    require(total == expected and sum(date_counts.values()) == sum(percent_counts.values()) == n,
            "literal field reconciliation")
    require(db.execute("SELECT count(*) FROM source_field_literals").fetchone()[0] == n,
            "literal table count")
    db.commit()
    check_integrity(db)
    require(not db.execute("PRAGMA foreign_key_check").fetchall(), "literal foreign key integrity")
    return {"association_format_counts": dict(date_counts), "percentage_format_counts": dict(percent_counts),
            "retained_literal_rows": n, "date_or_percentage_interpretation": "not_qualified"}

def archive(store, national, root):
    # Read existing receipt before any publisher download, so repeat runs are
    # idempotent and do not acquire an already archived source.
    receipt = storemod.existing(store, KEY, PIN)
    if receipt is not None:
        require(receipt["base_receipt_sha256"] == national["receipt_sha256"], "FS039 base receipt drift")
        verify_projection(receipt["summary"])
        return receipt
    raw = root / "source.csv"
    meta, expected = q.download(raw)
    require(meta["sha256"] == PIN and meta["released"] == RELEASE and expected == ROWS,
            "FS039 pinned publisher release changed")
    db_path = root / "projection.sqlite3"
    with closing(sqlite3.connect(db_path)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        with raw.open(encoding="utf-8-sig", newline="") as stream:
            summary = q.project(stream, expected, db)
        verify_projection(summary)
        with raw.open(encoding="utf-8-sig", newline="") as stream:
            formats = retain_literals(stream, db, expected)
    require(sha(raw) == PIN, "FS039 source integrity")
    raw.unlink()
    summary.pop("azure_writes", None)
    summary.update(organization_role_rows=STORED, qualification_run=QUALIFICATION_RUN,
                   literal_evidence=formats,
                   limits="Private organizational role observations; unresolved source literals are not interpreted. No individual owner records, raw publisher bytes, provider addresses, public promotion, canonical property ownership, verified current relationships or commercial reuse clearance.")
    audit = {"publisher": meta, "summary": summary, "projection_sha256": sha(db_path),
             "projection_bytes": db_path.stat().st_size, "reuse_review": "pending",
             "public_promotion": False}
    return storemod.publish(store, KEY, meta, db_path, audit, root, national)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--receipt", type=Path, required=True)
    args = p.parse_args()
    require(not args.receipt.exists(), "new receipt required")
    a.run_key(os.environ)
    store = storemod.SourceAzure(os.environ)
    try:
        national = storemod.national_manifest(store)
        with tempfile.TemporaryDirectory(prefix="fs039-private-") as tmp:
            receipt = archive(store, national, Path(tmp))
        with args.receipt.open("xb") as f:
            f.write(a.encode(receipt))
        print("PRIVATE_FS039_COMPLETE", json.dumps(receipt, sort_keys=True), flush=True)
    finally:
        store.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("PRIVATE_FS039_FAILED", type(e).__name__, flush=True)
        raise SystemExit(1) from None
