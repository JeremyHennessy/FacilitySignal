import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/"research"
class NPPESLedgerTests(unittest.TestCase):
    def test_weekly_increment_separate_from_facilities(self):
        l=json.loads((ROOT/"coverage_status.json").read_text())
        row=next(x for x in l["sources"] if x["id"]=="FS-004")
        b=l["nppes_v2_qualified_baselines"]["weekly"];a=b["audit"]
        self.assertEqual(row["status"],"partial_structural_qualification")
        self.assertEqual(a["scope"],"weekly")
        self.assertEqual(a["input_rows"],31024)
        self.assertEqual(sum(a["entity_classes"].values()),a["input_rows"])
        self.assertEqual(a["entity_classes"],{"individual_excluded":23616,"organization":6627,"untyped_with_deactivation":781})
        self.assertEqual(a["distinct_valid_organization_npis"],6627)
        self.assertEqual(a["duplicate_valid_organization_rows"],0)
        for field in a["organization_field_states"].values():self.assertEqual(sum(field.values()),6627)
        for ref in a["reference_files"].values():self.assertEqual(sum(ref["key_counts"].values()),ref["input_rows"])
        self.assertFalse(a["endpoint_values_parsed"])
        self.assertEqual(b["job_conclusion"],"success")
        self.assertEqual(row["retained_database_rows"],0)
        self.assertFalse(b["included_in_integrated_national_baseline"])
        self.assertFalse(b["included_in_expanded_projection_total"])
        self.assertEqual(row["reuse_review"],"pending")
