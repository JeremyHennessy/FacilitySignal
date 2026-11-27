"""Verify the existing PECOS semantic claims against pinned evidence and real importer code."""
import csv
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import collect_ownership as adapter
from integrate_ownership import PINS

ROOT = Path(__file__).resolve().parents[1]
AUDIT = "research/pecos_projection_reconciliation_20261127.json"
CROSS = "research/pecos_field_semantic_crosswalk_20261126.json"
RAW = "research/pecos_raw_field_profiles_20261126.json"
HEADERS = "research/care_compare_pecos_exact_headers_20261126.json"
SNAPSHOT = "research/snapshot_release_20261125.json"

def read(path):
    return json.loads((ROOT / path).read_text())

def blob(path):
    data = (ROOT / path).read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()

PROJECTED = {"enrollment": adapter.ENROLL, "owner": adapter.ORG, "chow": adapter.CHOW}
# These are intentional indexed duplicates of JSON fields, not extra source fields.
INDEXED = {
    "enrollment": {"enrollment_id": "ENROLLMENT ID", "pac_id": "ASSOCIATE ID", "ccn": "CCN", "npi": "NPI", "organization_name": "ORGANIZATION NAME"},
    "owner": {"enrollment_id": "ENROLLMENT ID", "pac_id": "ASSOCIATE ID", "owner_pac_id": "ASSOCIATE ID - OWNER", "owner_name": "ORGANIZATION NAME - OWNER", "role_code": "ROLE CODE - OWNER", "role_text": "ROLE TEXT - OWNER"},
    "chow": {"buyer_enrollment_id": "ENROLLMENT ID - BUYER", "seller_enrollment_id": "ENROLLMENT ID - SELLER", "buyer_ccn": "CCN - BUYER", "seller_ccn": "CCN - SELLER", "effective_date": "EFFECTIVE DATE"},
}

class PecosProjectionReconciliationTests(unittest.TestCase):
    def test_pinned_sources_and_every_field(self):
        audit = read(AUDIT)
        for path in (CROSS, RAW, HEADERS, SNAPSHOT):
            self.assertEqual(blob(path), audit["evidence_blobs"][path])
        cross = {s["source"]: s for s in read(CROSS)["sources"]}
        raw = {s["source"]: s for s in read(RAW)["sources"]}
        heads = {s["source"]: s for s in read(HEADERS)["sources"] if s["family"] == "pecos"}
        manifest = {s["key"]: s for s in read(SNAPSHOT)["sources"] if s["family"] == "pecos"}
        summaries = {s["source"]: s for s in audit["sources"]}
        self.assertEqual(set(cross), set(raw))
        self.assertEqual(set(cross), set(heads))
        self.assertEqual(set(cross), set(manifest))
        self.assertEqual(set(cross), set(summaries))
        self.assertEqual(set(cross), set(PINS))
        totals = dict(sources=len(cross), header_fields=0, publisher_definition_reviewed_fields=0,
                      existing_retained_field_occurrences=0, not_retained_field_occurrences=0,
                      presence_only_field_occurrences=0, lexical_only_semantic_review_fields=0,
                      input_rows=0, stored_rows=0, excluded_individual_rows=0,
                      new_domain_qualified_fields=0, new_application_approved_fields=0)
        for key, source in cross.items():
            with self.subTest(source=key):
                p, h, m, s = raw[key], heads[key], manifest[key], summaries[key]
                projected = set(PROJECTED[key.rsplit("-", 1)[1]])
                def names(obj):
                    return [(f["ordinal"], f["field"]) for f in obj["fields"]]
                self.assertEqual(names(source), names(p))
                self.assertEqual(names(source), names(h))
                self.assertEqual(len(set(f["field"] for f in source["fields"])), len(source["fields"]))
                self.assertEqual(source["source_sha256"], p["source_sha256"])
                self.assertEqual(source["period"], p["period"])
                self.assertEqual((p["source_sha256"], p["input_rows"], p["profiled_rows"], p["excluded_rows"]), PINS[key])
                self.assertEqual((m["sha256"], m["input_rows"], m["stored_rows"], m["excluded_rows"]), PINS[key])
                self.assertEqual(m["release"], p["period"])
                self.assertEqual(p["input_rows"], p["profiled_rows"] + p["excluded_rows"])
                self.assertEqual(projected, {f["field"] for f in source["fields"] if f["prior_projection_retained"]})
                self.assertEqual(len(source["fields"]), p["columns"])
                for f, profile in zip(source["fields"], p["fields"]):
                    self.assertEqual(f["raw_profile_status"], profile["profile_status"])
                    self.assertEqual(f["application_approval"], "no_new_row_level_approval")
                    self.assertEqual(f["semantic_status"], "publisher_definition_reviewed")
                    self.assertEqual(sum(profile.get("states", profile.get("presence", {})).values()), p["profiled_rows"])
                    if "presence" in profile["profile_status"]:
                        self.assertNotIn(f["field"], projected)
                presence = sum("presence" in f["profile_status"] for f in p["fields"])
                lexical = sum(f["value_review"] == "lexical_profile_only" for f in source["fields"])
                self.assertEqual(s, dict(source=key, source_sha256=p["source_sha256"], period=p["period"],
                    columns=len(source["fields"]), retained_fields=len(projected),
                    not_retained_fields=len(source["fields"])-len(projected), presence_only_fields=presence,
                    lexical_only_semantic_review_fields=lexical, input_rows=p["input_rows"],
                    stored_rows=p["profiled_rows"], excluded_individual_rows=p["excluded_rows"]))
                totals["header_fields"] += len(source["fields"])
                totals["publisher_definition_reviewed_fields"] += len(source["fields"])
                totals["existing_retained_field_occurrences"] += len(projected)
                totals["not_retained_field_occurrences"] += len(source["fields"])-len(projected)
                totals["presence_only_field_occurrences"] += presence
                totals["lexical_only_semantic_review_fields"] += lexical
                totals["input_rows"] += p["input_rows"]
                totals["stored_rows"] += p["profiled_rows"]
                totals["excluded_individual_rows"] += p["excluded_rows"]
        self.assertEqual(audit["totals"], totals)

    def test_real_importer_all_six_sources_and_sqlite_projection(self):
        sources = read(CROSS)["sources"]
        with tempfile.TemporaryDirectory() as directory, sqlite3.connect(":memory:") as db:
            db.row_factory = sqlite3.Row
            adapter.init(db)
            for source in sources:
                key = source["source"]
                kind = key.rsplit("-", 1)[1]
                with self.subTest(source=key):
                    names = [f["field"] for f in source["fields"]]
                    retained = {f["field"] for f in source["fields"] if f["prior_projection_retained"]}
                    row = {field: f"  fixture-{i}  " for i, field in enumerate(names)}
                    for field, val in {"ENROLLMENT ID": "O20070222000526", "ASSOCIATE ID": "0012345678",
                            "CCN": "012345", "ASSOCIATE ID - OWNER": "0001234567", "TYPE - OWNER": "O"}.items():
                        if field in row:
                            row[field] = val
                    path = Path(directory) / (key + ".csv")
                    expected = 2 if kind == "owner" else 1
                    with path.open("w", newline="", encoding="utf-8") as stream:
                        writer = csv.DictWriter(stream, fieldnames=names)
                        writer.writeheader()
                        writer.writerow(row)
                        if kind == "owner":
                            individual = {f: "INDIVIDUAL-MUST-NOT-PERSIST" for f in names}
                            individual["TYPE - OWNER"] = "I"
                            writer.writerow(individual)
                    meta = {"zipped": False, "period": "fixture", "modified": "fixture", "api": "fixture", "url": "fixture"}
                    result = adapter.ingest(db, key, meta, path, "fixture", expected)
                    self.assertEqual((result["input_rows"], result["stored_rows"], result["excluded_individual_rows"], result["rejected_rows"]), (expected, 1, expected-1, 0))
                    table = adapter.TABLES[kind]
                    records = db.execute("SELECT * FROM " + table + " WHERE source=?", (key,)).fetchall()
                    self.assertEqual(len(records), 1)
                    record = dict(records[0])
                    self.assertEqual(set(record), {"source", "ordinal", "projection"} | set(INDEXED[kind]))
                    self.assertEqual(record["ordinal"], 2)
                    self.assertEqual(json.loads(record["projection"]), {field: row[field].strip() for field in retained})
                    for column, field in INDEXED[kind].items():
                        self.assertEqual(record[column], row[field].strip())
                    self.assertNotIn("INDIVIDUAL-MUST-NOT-PERSIST", str(record))
                    if kind == "owner":
                        self.assertNotIn("TYPE - OWNER", json.loads(record["projection"]))
                    self.assertEqual(tuple(db.execute("SELECT expected_rows,stored_rows,excluded_individual_rows FROM pecos_releases WHERE source=?", (key,)).fetchone()), (expected, 1, expected-1))
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertFalse(db.execute("PRAGMA foreign_key_check").fetchall())
            for link in adapter.audit_linkage(db).values():
                self.assertEqual(link["org_role_rows_exact_enrollment_and_pac"], 1)
                self.assertEqual(link["unmatched_org_role_rows"], 0)
