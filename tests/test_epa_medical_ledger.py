import json
import unittest
from pathlib import Path
class MedicalLedgerTests(unittest.TestCase):
    def test_aggregate_evidence_does_not_waive_source_gate(self):
        p=Path(__file__).resolve().parents[1]/"research/coverage_status.json"
        e=next(x for x in json.loads(p.read_text())["sources"] if x["id"]=="FS-157")
        a=e["medical_area_aggregate"];self.assertEqual(a["source_sha256"],e["source_sha256"])
        self.assertEqual(sum(a["area_counts"].values()),e["retrieved_rows"])
        self.assertEqual(sum(a["area_by_identifier_state"]["documented_format"].values()),e["documented_format_rows"])
        self.assertEqual(sum(a["area_by_identifier_state"]["unresolved_format"].values()),e["unresolved_format_rows"])
        self.assertEqual(sum(a["exact_medical_area_activity_raw_code_counts"].values()),1712)
        self.assertEqual(a["area_by_identifier_state"]["unresolved_format"]["exact_code_and_description"],11)
        self.assertEqual(e["status"],"blocked_key_format_review");self.assertEqual(e["retained_database_rows"],0)
