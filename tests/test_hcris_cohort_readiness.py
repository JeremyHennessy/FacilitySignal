import copy
import unittest
from scripts.audit_hcris_cohort_readiness import audit, load_inputs, overlap_bounds

class HCRISCohortReadinessTests(unittest.TestCase):
    def test_pinned_evidence(self):
        out = audit(*load_inputs())
        h, s = (out["forms"][k] for k in ("hospital", "snf"))
        self.assertEqual((h["intersection"], h["candidates"], s["intersection"], s["candidates"]),
                         (4339, 3561, 13772, 13408))
        self.assertEqual(len(h["measures"]) + len(s["measures"]), 17)
        self.assertEqual(h["numeric_rows"] + s["numeric_rows"], 33209912)
        self.assertEqual(h["measures"]["Total Costs"]["minimum_candidate_equal"], 3482)
        self.assertEqual(s["measures"]["Contract Labor"]["minimum_candidate_equal"], 9751)
        self.assertEqual(s["measures"]["Contract Labor"]["maximum_candidate_equal"], 10115)
        self.assertFalse(out["public_promotion"])
        self.assertFalse(out["monetary_scale_qualified"])

    def test_bounds(self):
        self.assertEqual(overlap_bounds(10, 8, 7), (5, 7))
        self.assertEqual(overlap_bounds(10, 2, 3), (0, 2))
        with self.assertRaises(ValueError):
            overlap_bounds(10, 11, 7)

    def test_fail_closed(self):
        for section, field, value in ((0, "puf_sha256", "different"),
                                      (1, "nonconflicting_three_way_candidate_reports", 1),
                                      (2, "public_promotion", True)):
            inputs = copy.deepcopy(load_inputs())
            inputs[section]["forms"]["hospital"][field] = value
            with self.assertRaises(ValueError):
                audit(*inputs)
        inputs = copy.deepcopy(load_inputs())
        inputs[0]["forms"]["snf"]["measures"]["Contract Labor"]["comparisons"]["equal_decimal"] -= 1
        with self.assertRaises(ValueError):
            audit(*inputs)
