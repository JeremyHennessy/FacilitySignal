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

    def test_monthly_primary_and_reference_reconciliation(self):
        l=json.loads((ROOT/"coverage_status.json").read_text())
        row=next(x for x in l["sources"] if x["id"]=="FS-004")
        entries=l["nppes_v2_qualified_baselines"];b=entries["monthly"];a=b["audit"]
        self.assertEqual(row["status"],"partial_structural_qualification")
        self.assertEqual(a["scope"],"monthly")
        self.assertEqual(a["input_rows"],9891116)
        self.assertEqual(sum(a["entity_classes"].values()),a["input_rows"])
        self.assertEqual(a["entity_classes"],{"individual_excluded":7540866,"organization":1990237,"untyped_with_deactivation":360013})
        self.assertEqual(a["distinct_valid_organization_npis"],1990237)
        self.assertEqual(a["duplicate_valid_organization_rows"],0)
        self.assertEqual(a["organization_key_counts"],{"valid_organization_npi":1990237})
        for field in a["organization_field_states"].values():self.assertEqual(sum(field.values()),1990237)
        self.assertEqual(a["reference_files"]["other_name"]["key_counts"]["type2_key_match"],814577)
        self.assertEqual(a["reference_files"]["practice_location"]["key_counts"]["type2_key_match"],137312)
        for ref in a["reference_files"].values():self.assertEqual(sum(ref["key_counts"].values()),ref["input_rows"])
        self.assertFalse(a["endpoint_values_parsed"])
        self.assertFalse(b["included_in_integrated_national_baseline"])
        self.assertFalse(b["included_in_expanded_projection_total"])
        self.assertEqual(b["retained_row_level_records"],0)
        self.assertNotEqual(a["publisher"]["sha256"],entries["weekly"]["audit"]["publisher"]["sha256"])
        self.assertEqual(json.loads((ROOT/"expanded_source_lock_20261126.json").read_text())["source_count"],17)
