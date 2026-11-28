import json
import unittest
from scripts import qualify_snf24_cost_coverage as q

def header(end="09/30/2025"):
    return ("010101", "1", "09/30/2024", end)

def identity(end="09/30/2025"):
    return {"ccn": ["010101"], "begin": ["09/30/2024"], "end": [end]}

def cells(key="1", line="00500"):
    return [[key, "A000000", line, col, val] for col, val in zip(q.COLUMNS, ("10", "20", "30", "5", "35"))]

class CostCoverageTests(unittest.TestCase):
    def test_revision_boundary_and_exact_arithmetic(self):
        headers = {"1": header(), "2": header("06/30/2026"), "3": header("06/29/2026")}
        ids = {"1": identity(), "2": identity("06/30/2026"), "3": identity("06/29/2026")}
        a = q.audit(headers, ids, cells()+cells("2")+cells("3"))
        self.assertEqual(a["report_counts"], {"pre_rev3": 2, "rev3": 1})
        self.assertEqual(a["coordinate_count"], 24)
        self.assertEqual(a["equation_counts"]["pre_rev3"]["plant_maintenance_repairs"]["subtotal"], {"exact": 2})
        self.assertEqual(a["equation_counts"]["rev3"]["plant_maintenance_repairs"]["labor"], {"exact": 1})
        self.assertNotIn("010101", json.dumps(a))

    def test_absent_zero_and_duplicates(self):
        rows = [["1", "A000000", "00700", "00100", "0"],
                ["1", "A000000", "00700", "00200", "9"],
                ["1", "A000000", "00700", "00200", "9"],
                ["1", "A000000", "00700", "00400", "-1"]]
        a = q.audit({"1": header()}, {"1": identity()}, rows)
        d = a["coordinate_counts"]["pre_rev3"]["housekeeping"]
        self.assertEqual(d["employee_wages"], {"zero": 1})
        self.assertEqual(d["contract_labor"], {"duplicate_held": 1})
        self.assertEqual(d["nonlabor_costs"], {"negative": 1})
        self.assertEqual(d["labor_subtotal"], {"absent": 1})
        self.assertEqual(a["equation_counts"]["pre_rev3"]["housekeeping"]["labor"], {"incomplete": 1})

    def test_subscripts_and_identity_conflicts_held(self):
        a = q.audit({"1": header(), "2": header()}, {"1": identity(), "2": {}},
                    cells()+cells("1", "00501")+cells("2"))
        self.assertEqual(a["scan"]["subscript_rows_held"], 5)
        self.assertEqual(a["coordinate_counts"]["pre_rev3"]["plant_maintenance_repairs"]["contract_labor"], {"subscript_held": 1})
        self.assertEqual(a["coordinate_counts"]["unresolved"]["plant_maintenance_repairs"]["contract_labor"], {"identity_or_period_held": 1})

    def test_unequal_complete_equation_is_not_silently_corrected(self):
        rows = cells()
        rows[-1][-1] = "36"
        a = q.audit({"1": header()}, {"1": identity()}, rows)
        self.assertEqual(a["equation_counts"]["pre_rev3"]["plant_maintenance_repairs"]["subtotal"], {"unequal": 1})

    def test_orphan_and_invalid_width_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "orphan"):
            q.audit({"1": header()}, {"1": identity()}, cells("2"))
        with self.assertRaisesRegex(ValueError, "width"):
            q.audit({"1": header()}, {"1": identity()}, [["1"]])

    def test_no_coercion_and_capital_shaded_cells_excluded(self):
        for token in ("", "NaN", "Infinity", "1e4", "1,234", " 1", "+1", "+0"):
            self.assertIsNone(q.value(token))
        a = q.audit({"1": header()}, {"1": identity()}, cells(line="00100"))
        self.assertEqual(a["scan"]["other_base_column_rows"], 3)
        self.assertEqual(set(a["coordinate_counts"]["pre_rev3"]["building_fixture_costs"]), {"nonlabor_costs", "unadjusted_subtotal"})
