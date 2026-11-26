import json
import unittest
from pathlib import Path
from research_evidence import evidence

ROOT = Path(__file__).resolve().parents[1]
class ResearchEvidenceTests(unittest.TestCase):
    def test_reconcile_qualified_audits(self):
        l = json.loads((ROOT/"research/coverage_status.json").read_text())
        d = evidence(ROOT/"research/coverage_status.json")
        a = d["citation_dictionary"]["audit"]
        b = d["service_context"]["audit"]
        old = l["citation_evidence_qualified_baseline"]
        self.assertEqual(a["citation_source_sha256"], b["source_database_sha256"])
        self.assertEqual(b["source_database_sha256"], old["source_database_sha256"])
        self.assertEqual(a["citation_rows"], b["citation_rows"])
        self.assertEqual(b["citation_rows"], old["citation_rows"])
        self.assertEqual(a["lookup"]["rows"], sum(a["lookup"]["keys_by_prefix"].values()))
        self.assertEqual(a["lookup"]["distinct_keys"], 643)
        self.assertEqual(sum(v["lookup_match_counts"].get("exact_text_single_definition",0) for v in a["sources"].values()),610749)
        for key, source in b["sources"].items():
            prior = a["sources"][key]
            self.assertEqual(source["rows"], prior["rows"])
            self.assertEqual(source["literal_status_counts"], prior["correction_status_candidate_counts"])
            for field in ("date_state_counts","research_context_counts","literal_status_counts"):
                self.assertEqual(sum(source[field].values()), source["rows"])
        self.assertEqual(sum(v["date_state_counts"].get("on_or_before_release/after_release",0) for v in b["sources"].values()),old["correction_dates_after_release"])
        self.assertEqual(b["confirmed_opportunities"],0)
        self.assertFalse(d["live_database_verified"])
        self.assertFalse(d["retention_checkpoint"]["durable_private_storage_verified"])
        self.assertEqual(d["retention_checkpoint"]["artifact_id"], b["source_artifact_id"])
        self.assertNotIn("sources",d)
