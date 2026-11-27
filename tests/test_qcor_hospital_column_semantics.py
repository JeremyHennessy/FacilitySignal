import hashlib
import json
from pathlib import Path
import unittest
import sqlite3
import collect_qcor_hospital as adapter

ROOT = Path(__file__).resolve().parents[1]
class QcorColumnSemanticsTests(unittest.TestCase):
    def test_pinned_profile_and_header(self):
        audit = json.loads((ROOT / "research/qcor_hospital_column_semantics_20261127.json").read_text())
        raw = (ROOT / audit["profile_path"]).read_bytes()
        self.assertEqual(hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest(), audit["profile_blob"])
        source = json.loads(raw)["sources"][0]
        self.assertEqual(audit["source_sha256"], source["source_sha256"])
        self.assertEqual(audit["source_rows"], source["profiled_rows"])
        self.assertEqual(tuple(f["field"] for f in audit["fields"]), adapter.HEADER)
        self.assertEqual([f["profile"] for f in audit["fields"]], source["fields"])
        for f in audit["fields"]:
            self.assertFalse(f["observed_domain_qualified"])
            self.assertFalse(f["new_application_approved"])
            p = f["profile"]
            self.assertEqual(sum(p.get("states", p.get("presence", {})).values()), audit["source_rows"])
        with sqlite3.connect(":memory:") as db:
            db.executescript((ROOT / "schema.sql").read_text())
            columns = [r[1] for r in db.execute("PRAGMA table_info(qcor_hospital_rows)")]
        self.assertEqual([f["adapter_projection"] for f in audit["fields"][:14]], columns[3:-1])
        self.assertEqual(sum(f["adapter_projection"] is not None for f in audit["fields"]), 14)
        self.assertTrue(all(f["disposition"] == "excluded_narrative" for f in audit["fields"][14:]))

    def test_distinct_grains_and_missing_markers(self):
        audit = json.loads((ROOT / "research/qcor_hospital_column_semantics_20261127.json").read_text())
        g = audit["grain"]
        self.assertEqual(g["tag_rows"] + g["memo_rows"] + g["no_tag_rows"], g["source_rows"])
        self.assertEqual(g["source_event_groups"] - g["groups_without_nonmemo_tags"], g["groups_with_nonmemo_tags"])
        self.assertEqual(audit["publisher_evidence"]["report_default_records"] - g["groups_with_nonmemo_tags"], 765)
        self.assertEqual(audit["fields"][10]["profile"]["literal_marker_counts"]["n/a"], 7)
        self.assertEqual(audit["fields"][13]["profile"]["literal_marker_counts"]["n/a"], 79)
        self.assertEqual(audit["totals"]["new_application_approved_fields"], 0)
