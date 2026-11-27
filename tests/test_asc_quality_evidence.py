import json
import unittest
from pathlib import Path
from scripts import qualify_asc_quality as q

ROOT=Path(__file__).resolve().parents[1]

class ASCQualityEvidenceTests(unittest.TestCase):
    def test_pinned_aggregate_and_ledger(self):
        receipt=json.loads((ROOT/"research/fs041_asc_quality_qualification_20261127.json").read_text())
        a=receipt["audit"]
        self.assertEqual(receipt["run"],46043049342)
        self.assertEqual(a["input_rows"],5786)
        self.assertEqual(a["source_columns"],47)
        self.assertEqual(set(a["field_presence_profiles"]),set(q.HEADER))
        self.assertTrue(all(sum(p.values())==a["input_rows"] for p in a["field_presence_profiles"].values()))
        self.assertEqual(a["distinct_facility_year_keys"]+a["repeated_facility_year_rows"]+a["missing_or_unreviewed_facility_year_rows"],a["input_rows"])
        self.assertEqual(sum(a["jurisdiction_row_counts"].values()),a["input_rows"])
        self.assertEqual(a["report_years"],{"2025":5786})
        self.assertEqual(a["row_level_retained"],0)
        self.assertEqual(a["canonical_matches"],0)
        self.assertEqual(a["azure_writes"],0)
        self.assertFalse(a["public_promotion"])
        self.assertEqual(a["reuse_review"],"pending")
        ledger=json.loads((ROOT/"research/coverage_status.json").read_text())
        entry=next(x for x in ledger["sources"] if x["id"]=="FS-041")
        self.assertEqual(entry["status"],"aggregate_screening_qualified")
        self.assertEqual(entry["source_sha256"],a["publisher"]["sha256"])
        self.assertEqual(entry["source_records"],a["input_rows"])
        self.assertEqual(entry["retained_database_rows"],0)
