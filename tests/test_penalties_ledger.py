import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/"research"
class PenaltiesLedgerTests(unittest.TestCase):
    def test_ephemeral_qualification(self):
        ledger=json.loads((ROOT/"coverage_status.json").read_text())
        row=next(x for x in ledger["sources"] if x["id"]=="FS-036")
        baseline=ledger["cms_penalties_qualified_baseline"];a=baseline["audit"]
        self.assertEqual(row["status"],"ephemeral_projection_qualified")
        self.assertEqual(a["input_rows"],a["stored_rows"])
        self.assertEqual(a["stored_rows"],row["ephemeral_projected_rows"])
        self.assertEqual(sum(a["penalty_type_counts"].values()),a["stored_rows"])
        self.assertEqual(a["link_counts"],{"same_state":15007})
        self.assertEqual(a["rejected_rows"]+a["exact_duplicate_rows"]+a["duplicate_fine_ids"],0)
        self.assertEqual(row["retained_database_rows"],0)
        self.assertFalse(baseline["included_in_integrated_national_baseline"])
        self.assertEqual(baseline["run"],int(row["evidence"]))
        self.assertEqual(len(ledger["sources"]),176)
        self.assertEqual(json.loads((ROOT/"snapshot_release_20261125.json").read_text())["source_records_total"],1904060)
