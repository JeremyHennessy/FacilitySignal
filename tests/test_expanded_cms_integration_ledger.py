import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/"research"
class ExpandedCMSIntegrationLedgerTests(unittest.TestCase):
    def test_combined_scope_reconciliation(self):
        l=json.loads((ROOT/"coverage_status.json").read_text())
        b=l["expanded_cms_integration_baseline"];a=b["audit"]
        self.assertEqual(a["original_table_rows"],{"current_release":9,"facilities":48004,"findings":619069,"releases":9})
        self.assertEqual(a["original_primary_source_rows"],667073)
        self.assertEqual(a["extension_source_rows"],228590)
        self.assertEqual(a["combined_primary_source_rows"],895663)
        self.assertEqual(sum(x["rows"] for x in a["sources"].values()),228590)
        self.assertEqual(a["citation_ccn_day_crosscheck"],{"same_ccn_day":619069})
        self.assertTrue(a["original_tables_content_verified"])
        self.assertEqual(a["integrity_check"],"passed")
        self.assertEqual(b["retained_row_level_records"],0)
        self.assertFalse(b["included_in_original_19_source_national_baseline"])
        for sid,x in a["sources"].items():
            r=next(y for y in l["sources"] if y["id"]==sid)
            self.assertEqual(r["combined_care_compare_qualified_rows"],x["rows"])
            self.assertEqual(r["combined_care_compare_qualification_run"],b["run"])
            self.assertEqual(r["retained_database_rows"],0)
        self.assertEqual(json.loads((ROOT/"snapshot_release_20261125.json").read_text())["source_records_total"],1904060)
    def test_340b_timeout_is_not_ingestion(self):
        l=json.loads((ROOT/"coverage_status.json").read_text())
        row=next(x for x in l["sources"] if x["id"]=="FS-017")
        b=l["hrsa_340b_report_blocker"];a=b["audit"]
        self.assertEqual(row["status"],"blocked_report_download")
        self.assertEqual(row["retrieved_rows"],0)
        self.assertIsNone(a["publisher"])
        self.assertEqual(a["failure"]["reason"],"public report download timed out")
        self.assertFalse(b["qualified"])
        self.assertEqual(b["retained_row_level_records"],0)
