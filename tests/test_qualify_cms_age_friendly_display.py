import unittest
from scripts.qualify_cms_age_friendly_display import qualify

R=[(f"AFH_S{i}_N_RATE",f"Hospitals Scoring {i} out of 5 points - Fixture","Hospital Measure",
    "Age Friendly Hospital Measure",str(v),"","01/01/2025","12/31/2025")
    for i,v in enumerate((5,10,15,20,20,30))]

class DisplayTests(unittest.TestCase):
    def test_values_do_not_create_a_denominator(self):
        r=qualify(R,"2026-11-12")
        self.assertEqual(r["sum_of_displayed_scores"],100)
        self.assertIsNone(r["reporting_denominator"])
        self.assertEqual(r["facility_attestations_or_links_emitted"],0)

    def test_wrong_gauge_window_and_missing_rejected(self):
        for idx,val in ((0,"PSSM_S5_N_RATE"),(1,"Hospitals Scoring 4 out of 5 points"),(4,"Not Available"),(7,"12/31/2026")):
            bad=list(R[-1]);bad[idx]=val
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                qualify(R[:-1]+[bad],"2026-11-12")

if __name__=="__main__":
    unittest.main()
