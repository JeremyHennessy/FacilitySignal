import unittest
from scripts import audit_irf_parent_field_availability as a


class IRFParentFieldAvailability(unittest.TestCase):
    def test_pinned_source_evidence(self):
        r = a.audit()
        self.assertEqual(r["qies_fields"]["PARENT_PROVIDER_NUMBER"],
                         {"blank": 13598, "other_states": 0, "ordinal": 136,
                          "historical_category_scopes": ["12", "14"]})
        self.assertEqual(r["qies_fields"]["REHAB_UNIT_SW"]["other_states"], 13589)
        self.assertEqual(r["qies_fields"]["REHAB_UNIT_EFCTV_DT"]["other_states"], 1652)
        self.assertEqual(r["pecos_reh_predecessor_reference"]["other_states"], 51)
        self.assertEqual(r["confirmed_irf_parent_links"], 0)

    def test_fail_closed(self):
        for states in ({"blank": 2}, {"blank": -1, "other_nonblank": 4}, {"blank": True}):
            with self.assertRaises(ValueError):
                a.reconcile({"states": states}, 3)
        with self.assertRaises(ValueError):
            a.unique([{"field": "x"}, {"field": "x"}], "field", "x")
