import unittest
from datetime import date
from scripts import qualify_snf_legacy_measure_semantics as gate


class SnfLegacyMeasureTest(unittest.TestCase):
    def test_actual_pinned_aggregate_evidence(self):
        result = gate.qualify(gate.SOURCE.read_bytes())
        self.assertEqual(result["matched_reports"], 13772)
        self.assertEqual(len(result["measures"]), 8)
        contract = result["measures"]["Contract Labor"]
        self.assertEqual((contract["matched_report_present"], contract["matched_report_missing"]), (10115, 3657))
        self.assertTrue(all(not m["publication_clearance"] and not m["monetary_scale_qualified"] for m in result["measures"].values()))
        self.assertEqual(result["row_values_read_or_retained"], 0)
        self.assertFalse(result["occupancy_ratio_qualified"])

    def test_revised_period_end_controls_transition(self):
        self.assertEqual(gate.form_gate("2540-10", date(2024, 10, 1), date(2025, 9, 29)), "legacy_map_candidate")
        self.assertEqual(gate.form_gate("2540-10", date(2024, 9, 30), date(2025, 9, 30)), "form_period_conflict")
        self.assertEqual(gate.form_gate("2540-24", date(2024, 9, 30), date(2025, 9, 30)), "new_form_mapping_required")
        self.assertEqual(gate.form_gate("2540-24", date(2024, 10, 1), date(2025, 9, 29)), "form_period_conflict")

    def test_unknown_form_invalid_period_and_changed_pin_fail_closed(self):
        self.assertEqual(gate.form_gate(None, date(2024, 1, 1), date(2024, 12, 31)), "unresolved_form")
        self.assertEqual(gate.form_gate("2540-10", None, date(2024, 12, 31)), "unresolved_period")
        self.assertEqual(gate.form_gate("2540-10", date(2024, 12, 31), date(2024, 1, 1)), "unresolved_period")
        with self.assertRaisesRegex(ValueError, "blob mismatch"):
            gate.qualify(gate.SOURCE.read_bytes() + b" ")
