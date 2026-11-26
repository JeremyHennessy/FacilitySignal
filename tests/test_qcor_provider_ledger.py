import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/"research"
class QCORProviderLedgerTests(unittest.TestCase):
    def test_qualification_grain_and_publication_boundary(self):
        l=json.loads((ROOT/"coverage_status.json").read_text())
        for key,sid,n,events,providers in (("asc","FS-025",61443,13755,4482),("xray","FS-028",751,418,347)):
            row=next(s for s in l["sources"] if s["id"]==sid)
            b=l["qcor_provider_qualified_baselines"][key];a=b["audit"]
            self.assertEqual(row["status"],"ephemeral_projection_qualified")
            self.assertEqual(a["source_id"],sid)
            self.assertEqual((a["input_rows"],a["stored_rows"],a["rejected_rows"]),(n,n,0))
            self.assertEqual(sum(a["row_kinds"].values()),n)
            self.assertEqual(a["distinct_survey_event_keys"],events)
            self.assertEqual(a["distinct_provider_keys"],providers)
            self.assertEqual(a["events_with_nonmemo_tag"]+a["events_without_nonmemo_tag"],events)
            self.assertEqual(row["retained_database_rows"],0)
            self.assertEqual(a["retained_row_level_records"],0)
            self.assertFalse(b["included_in_integrated_national_baseline"])
            self.assertEqual(row["reuse_review"],"pending")
        self.assertEqual(len(l["sources"]),176)
        self.assertEqual(json.loads((ROOT/"snapshot_release_20261125.json").read_text())["source_records_total"],1904060)
