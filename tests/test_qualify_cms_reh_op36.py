import unittest
from scripts.qualify_cms_reh_op36 import qualify

N=[["REH_OP_36","Not Available","0","2","0","4","5","01/01/2024","12/31/2024"]]
P=[["REH_OP_36","Not Available",*["Not Available"]*4,"7","01/01/2024","12/31/2024"],
   ["REH_OP_36","No Different than expected","31","0","0","1.7","","01/01/2024","12/31/2024"]]

class DisplayCases(unittest.TestCase):
    def test_missing_national_rate_does_not_erase_provider_numeric_zero(self):
        r=qualify(N,P,release="2026-11-12")
        self.assertEqual(r["national_rate_status"],"source_not_available_not_zero")
        self.assertEqual(r["provider_preview_score_dispositions"],
                         {"no_eligible_cases":1,"numeric_with_reported_interval":1})
        self.assertFalse(r["national_counts_used_as_provider_denominator"])

    def test_invalid_or_cross_program_input_rejected(self):
        for ix,value in ((0,"OP_36"),(8,"12/31/2025"),(3,"NaN"),(4,"2"),(6,"5")):
            row=P[-1].copy()
            row[ix]=value
            with self.subTest(row=row),self.assertRaises(ValueError):
                qualify(N,[row],release="2026-11-12")
        with self.assertRaises(ValueError):
            qualify(N,P,release="2026-05-13")

if __name__=="__main__":
    unittest.main()
