import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]/"research"

class MQSALedgerTests(unittest.TestCase):
    def test_mqsa_is_separate_ephemeral_qualification(self):
        ledger=json.loads((ROOT/"coverage_status.json").read_text())
        row=next(x for x in ledger["sources"] if x["id"]=="FS-011")
        baseline=ledger["fda_mqsa_qualified_baseline"]
        audit=baseline["audit"]
        self.assertEqual(row["status"],"ephemeral_projection_qualified")
        self.assertEqual(row["ephemeral_projected_rows"],audit["stored_rows"])
        self.assertEqual(audit["input_rows"],audit["stored_rows"])
        self.assertEqual(sum(audit["jurisdiction_counts"].values()),audit["stored_rows"])
        self.assertEqual(audit["layout_valid_row_counts"]["pipe"]+audit["schema_exception_rows"],audit["stored_rows"])
        self.assertEqual(audit["pipe_rejection_reason_counts"],{"width_address1":6})
        self.assertEqual(audit["represented_us_jurisdictions"],56)
        self.assertEqual(audit["canonical_matches"]+audit["unresolved_rows"]+audit["exact_parsed_row_duplicates"]+audit["repeated_projected_name_address_rows"],0)
        self.assertEqual(row["retained_database_rows"],0)
        self.assertEqual(baseline["retained_row_level_records"],0)
        self.assertFalse(baseline["included_in_integrated_national_baseline"])
        self.assertFalse(audit["stable_publisher_id_available"])
        self.assertEqual(row["reuse_review"],"pending")
        self.assertEqual(baseline["run"],int(row["evidence"]))
        self.assertEqual(len(ledger["sources"]),176)
        self.assertEqual(json.loads((ROOT/"snapshot_release_20261125.json").read_text())["source_records_total"],1904060)

    def test_hrsa_remains_unretrieved(self):
        ledger=json.loads((ROOT/"coverage_status.json").read_text())
        row=next(x for x in ledger["sources"] if x["id"]=="FS-009")
        self.assertEqual(row["status"],"publisher_documentation_reviewed")
        self.assertEqual(row["retrieved_rows"],0)
        self.assertEqual(row["reuse_review"],"pending")
