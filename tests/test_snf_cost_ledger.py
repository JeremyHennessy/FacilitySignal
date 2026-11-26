import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/"research"
class SNFCostLedgerTests(unittest.TestCase):
    def test_report_scope_and_reconciliation(self):
        l=json.loads((ROOT/"coverage_status.json").read_text())
        row=next(s for s in l["sources"] if s["id"]=="FS-057")
        b=l["snf_cost_qualified_baseline"];a=b["audit"]
        self.assertEqual(row["status"],"ephemeral_projection_qualified")
        self.assertEqual(a["input_rows"],a["stored_rows"]+a["rejected_rows"])
        self.assertEqual((a["stored_rows"],a["rejected_rows"],a["exact_duplicate_rows"]),(14587,0,0))
        self.assertEqual(sum(a["link_counts"].values()),14587)
        self.assertEqual(a["link_counts"],{"same_state":14416,"unmatched_ccn":171})
        self.assertEqual(len(a["measure_value_states"]),15)
        for counts in a["measure_value_states"].values():self.assertEqual(sum(counts.values()),14587)
        self.assertEqual(a["retained_row_level_records"],0)
        self.assertEqual(row["retained_database_rows"],0)
        self.assertFalse(b["included_in_integrated_national_baseline"])
        self.assertEqual(row["reuse_review"],"pending")
        self.assertEqual(len(l["sources"]),176)
        self.assertEqual(json.loads((ROOT/"snapshot_release_20261125.json").read_text())["source_records_total"],1904060)
