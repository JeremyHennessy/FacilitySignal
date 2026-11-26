"""One-time read-only restore of representative pinned FacilitySignal projections.
No publisher access, Azure writes, raw publication, or pointer changes.
"""
import argparse
import json
import os
import tempfile
from contextlib import closing
from pathlib import Path

import azure_national_archive as archive
from build_combined import require, readonly, check_integrity, sha
from scripts import audit_azure_archive_inventory as inventory
from scripts import azure_verified_extension as ext
from scripts import recover_azure_extension as recovery
from scripts import azure_source_archive as sources

# Exact scope for the 2026-11-26 archive. Additional source releases need a new audit.
SAMPLES = {
    "hha-organizational-ownership": {"pecos_org_role_rows": 21734, "pecos_enrollment_rows": 0, "pecos_chow_rows": 0},
    "hcris-cmhc-2017-index": {"reports": 716},
    "hcris-cmhc-2017-numeric": {"numeric_cells": 52390},
    "institutional-field-observations": {"candidate_provider": 27592, "candidate_field": 10, "candidate_observation": 101534},
}
EXPECTED_TOTALS = (212, 10908812534, 56, 117850722)

def validate_projection(path, expected):
    with closing(readonly(path)) as db:
        check_integrity(db)
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result = {}
        for table, count in expected.items():
            require(table in names and table.isidentifier(), "missing expected projection table")
            actual = db.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0]
            require(actual == count, "restored projection count mismatch: " + table)
            result[table] = actual
    return result

def restore_projection(store, national, pin, root, expected):
    name = sources.prefix_for(pin["key"], pin["source_sha256"]) + "/complete.json"
    rec, digest, head = ext.read_small(store, name)
    inventory.source_matches(rec, pin, national)
    root.mkdir(mode=0o700)
    for file in pin["files"]:
        ext.fetch_verified(store, rec["payload_prefix"] + "/" + file["path"], file, root / file["path"])
    db_pin = next(f for f in pin["files"] if f["path"] == "projection.sqlite3")
    path = root / "projection.sqlite3"
    counts = validate_projection(path, expected)
    require(sha(path) == db_pin["sha256"], "restored projection mutated")
    require(ext.read_small(store, name, digest)[2] == head, "projection receipt changed")
    return {"source_sha256": pin["source_sha256"], "database_sha256": db_pin["sha256"], "database_bytes": db_pin["bytes"], "table_counts": counts, "sqlite_integrity": "passed"}

def restore(store, ledger, root):
    totals = inventory.totals(ledger)
    require(tuple(totals[k] for k in ("payload_files", "payload_bytes", "publisher_releases", "source_observations")) == EXPECTED_TOTALS, "one-time audit inventory changed")
    national = ext.national_manifest(store)
    base, base_audit = ext.restore_national(store, national, root / "national")
    pointer, pointer_sha, pointer_head = ext.read_small(store, ext.EXT_POINTER)
    require(pointer["release"] == ledger["layers"][1]["release"], "extension pointer changed")
    rec, receipt_sha, receipt_head = ext.read_small(store, pointer["receipt"], pointer["receipt_sha256"])
    pin = recovery.load_pin()
    records = recovery.validate_receipt(rec, national, pin)
    for file in records:
        ext.fetch_verified(store, rec["payload_prefix"] + "/" + file["path"], file, root / file["path"])
    require(sha(root / "expanded-source-lock.json") == sha(inventory.ROOT / "research/expanded_source_lock_20261126.json"), "extension source lock mismatch")
    validation = recovery.verify_db(root / "extension.sqlite3", json.loads((root / "extension-audit.json").read_text()), rec, pin, base)
    selected = {}
    for key, expected in SAMPLES.items():
        matches = [x for x in ledger["receipts"] if x["key"] == key]
        require(len(matches) == 1, "sample receipt missing or ambiguous")
        selected[key] = restore_projection(store, national, matches[0], root / key, expected)
    ext.unchanged(store, national)
    require(ext.read_small(store, pointer["receipt"], receipt_sha)[2] == receipt_head, "extension receipt changed")
    require(ext.read_small(store, ext.EXT_POINTER, pointer_sha)[2] == pointer_head, "extension pointer changed")
    return {"status": "PASS", "scope": "representative pinned private archive restoration only", "national": {"source_records": base_audit["source_records_total"], "database_sha256": national["receipt"]["database_sha256"], "table_counts": base_audit["table_counts"], "sqlite_integrity": "passed"}, "extension": {**validation, "database_sha256": rec["database_sha256"]}, "supplemental": selected, "publisher_downloads": 0, "writes": 0, "public_promotion": False}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--receipt", type=Path, required=True)
    args = p.parse_args()
    require(not args.receipt.exists(), "receipt exists")
    archive.run_key(os.environ)
    store = inventory.ReadOnlyAzure(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="facilitysignal-readonly-restore-") as tmp:
            result = restore(store, json.loads(inventory.LEDGER.read_text()), Path(tmp))
    finally:
        store.close()
    with args.receipt.open("xb") as out:
        out.write(archive.encode(result))
    print("FACILITYSIGNAL_REPRESENTATIVE_RESTORE_VERIFIED", json.dumps(result, sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
