import json
import unittest
from pathlib import Path
from scripts import qualify_ltch_quality as q

ROOT=Path(__file__).resolve().parents[1]

class LTCHQualityEvidenceTests(unittest.TestCase):
    def test_pinned_sources_and_ledger(self):
        receipt=json.loads((ROOT/"research/fs042_ltch_quality_qualification_20261127.json").read_text())
        a=receipt["audit"]
        self.assertEqual(receipt["run"],46070464820)
        self.assertEqual(a["input_rows"],24285)
        self.assertEqual(set(a["sources"]),set(q.SPECS))
        self.assertEqual(a["sources"]["provider"]["distinct_expected_identifier_tokens"],311)
        self.assertEqual(a["sources"]["provider"]["jurisdictions"],47)
        self.assertEqual(a["sources"]["provider"]["distinct_measure_code_tokens"],78)
        for kind, item in a["sources"].items():
            ident, modified, count, header=q.SPECS[kind]
            self.assertEqual(item["input_rows"],count)
            self.assertEqual(item["publisher"]["id"],ident)
            self.assertEqual(item["publisher"]["modified"],modified)
            self.assertEqual(item["publisher"]["released"],q.RELEASE)
            self.assertEqual(set(item["field_presence"]),set(header))
            self.assertTrue(all(sum(x.values())==count for x in item["field_presence"].values()))
            self.assertEqual(item["provisional_distinct_keys"]+item["repeated_key_rows"]+item["unresolved_key_rows"],count)
            self.assertEqual(sum(item["date_window_states"].values()),count)
            self.assertRegex(item["publisher"]["sha256"],r"^[0-9a-f]{64}$")
        self.assertEqual(a["row_level_retained"],0)
        self.assertEqual(a["azure_writes"],0)
        self.assertEqual(a["canonical_matches"],0)
        self.assertFalse(a["public_promotion"])
        self.assertEqual(a["reuse_review"],"pending")
        coverage=json.loads((ROOT/"research/coverage_status.json").read_text())
        entry=next(x for x in coverage["sources"] if x["id"]=="FS-042")
        self.assertEqual(entry["status"],"aggregate_screening_qualified")
        self.assertEqual(entry["source_records"],a["input_rows"])
        self.assertEqual(entry["retained_database_rows"],0)
        self.assertEqual({x["dataset_id"]:x["source_sha256"] for x in entry["source_releases"]},
                         {x["publisher"]["id"]:x["publisher"]["sha256"] for x in a["sources"].values()})
