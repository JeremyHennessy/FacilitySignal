from dataclasses import replace
from fractions import Fraction
import unittest
from scripts.cms_hai_program_context import COMPARE,HAC_FY2026,HAC_FY2028,guard,key_compatible

class ProgramContextTests(unittest.TestCase):
    def test_exact_observed_edition_only(self):
        nation,provider=COMPARE
        metric="HAI_1_SIR"
        self.assertEqual(guard(provider,nation,metric,metric),"same_context_benchmark_only")
        self.assertEqual(guard(provider,provider,metric,metric),"unsupported_reporting_grains")
        self.assertEqual(guard(provider,nation,metric,"HAI_1_CIUPPER"),"different_or_unsupported_measure")
        self.assertEqual(guard(provider,HAC_FY2026,metric,metric),"different_reporting_programs")
        self.assertEqual(guard(provider,HAC_FY2028,metric,metric),"unknown_or_unobserved_edition")
        self.assertEqual(guard(provider,replace(nation,baseline_year=2015),metric,metric),
                         "unknown_or_unobserved_edition")

    def test_structural_comparison_holds_model_and_period_separate(self):
        start=("2025-01-01","2025-12-31")
        self.assertEqual(key_compatible("care_compare",2015,start,"care_compare",2022,start),"different_baseline")
        self.assertEqual(key_compatible("care_compare",2022,start,"hacrp",2022,start),"different_reporting_programs")
        self.assertEqual(key_compatible("care_compare",2022,start,"care_compare",2022,("2025-01-01","2026-12-31")),
                         "different_performance_period")
        self.assertEqual(key_compatible("care_compare",2022,start,"care_compare",2022,("2025-02-30","2025-12-31")),
                         "unknown_period")
        self.assertEqual(key_compatible("care_compare",None,start,"care_compare",2022,start),"unknown_baseline")

    def test_same_observed_count_can_cross_reference_one(self):
        self.assertLess(Fraction(6,8),1)
        self.assertGreater(Fraction(6,5),1)
        self.assertEqual(Fraction(6,8)*8,Fraction(6,5)*5)

if __name__=="__main__":
    unittest.main()
