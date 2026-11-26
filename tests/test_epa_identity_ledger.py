import json
import unittest
from collections import Counter
from pathlib import Path
from scripts.audit_epa_medical_identity import PINS

class IdentityLedgerTests(unittest.TestCase):
    def test_reconcile_qualified_aggregate_without_promoting_rows(self):
        ledger=json.loads((Path(__file__).resolve().parents[1]/"research/coverage_status.json").read_text())
        e=next(x for x in ledger["sources"] if x["id"]=="FS-157")
        a=e["medical_identity_aggregate"];b=e["medical_area_aggregate"]
        self.assertEqual(a["epa_source_sha256"],e["source_sha256"])
        self.assertEqual(a["cms_directory_git_blobs"],PINS)
        self.assertEqual(a["source_rows"],e["retrieved_rows"])
        self.assertEqual(a["medical_area_rows"],b["area_counts"]["exact_code_and_description"])
        self.assertEqual(sum(a["candidate_state_counts"].values()),a["medical_area_rows"])
        self.assertEqual(a["candidate_state_counts"]["unresolved_identifier"],b["area_by_identifier_state"]["unresolved_format"]["exact_code_and_description"])
        total=Counter()
        for k,v in a["raw_water_activity_by_candidate_state"].items():
            self.assertEqual(sum(v.values()),a["candidate_state_counts"][k]);total.update(v)
        self.assertEqual(dict(total),b["exact_medical_area_activity_raw_code_counts"])
        self.assertEqual(sum(a["candidate_pairs_by_cms_dataset"].values()),a["candidate_pairs"])
        self.assertLessEqual(a["distinct_cms_source_rows_in_candidates"],a["candidate_pairs"])
        self.assertGreaterEqual(a["candidate_pairs"],a["candidate_state_counts"]["one_candidate"]+2*a["candidate_state_counts"]["multiple_candidates"])
        self.assertEqual(e["retained_database_rows"],0)
        self.assertEqual(e["status"],"blocked_key_format_review")
        self.assertEqual(a["reuse_review"],"pending")
