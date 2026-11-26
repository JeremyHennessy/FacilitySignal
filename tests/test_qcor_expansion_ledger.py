import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/"research"
class QCORExpansionLedgerTests(unittest.TestCase):
    def test_completed_source_jobs_and_publication_boundary(self):
        l=json.loads((ROOT/"coverage_status.json").read_text())
        entries=l["qcor_expansion_qualified_baselines"]
        self.assertTrue({"cah","transplant","rhc","fqhc","prtf","corf","hha"}<=set(entries))
        for key,b in entries.items():
            a=b["audit"];row=next(s for s in l["sources"] if s["id"]==a["source_id"])
            self.assertEqual(a["input_rows"],a["stored_rows"]+a["rejected_rows"])
            self.assertEqual(sum(a["row_kinds"].values()),a["stored_rows"])
            self.assertEqual(a["events_with_nonmemo_tag"]+a["events_without_nonmemo_tag"],a["distinct_survey_event_keys"])
            self.assertEqual(row["status"],"ephemeral_projection_qualified" if b["job_conclusion"]=="success" else "blocked_key_format_review")
            self.assertEqual(row["retained_database_rows"],0)
            self.assertEqual(a["retained_row_level_records"],0)
            self.assertFalse(b["included_in_integrated_national_baseline"])
            self.assertEqual(row["reuse_review"],"pending")
        self.assertEqual(len(l["sources"]),176)
        self.assertEqual(json.loads((ROOT/"snapshot_release_20261125.json").read_text())["source_records_total"],1904060)
