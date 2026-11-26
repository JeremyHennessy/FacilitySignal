import unittest
from datetime import date
from scripts.qualify_hcris_three_way import documented_date,assess,FIELDS
class ThreeWayTest(unittest.TestCase):
    def test_documented_date_no_locale_fallback(self):
        self.assertEqual(documented_date("1/7/2024"),(date(2024,1,7),"mdy_ambiguous_without_documentation"))
        self.assertEqual(documented_date("2024-01-07"),(date(2024,1,7),"iso"))
        self.assertEqual(documented_date("31/12/2024"),(None,"invalid_mdy"))
        self.assertIsNone(documented_date("02/30/2024")[0])
    def test_three_observations_and_exclusions(self):
        headers={str(i):("012345","1/7/2024","12/31/2024") for i in range(1,6)}
        puf={k:("012345","NY","2024-01-07","2024-12-31") for k in headers}
        alpha={k:{"ccn":["012345"],"state":["NY"],"begin":["01/07/2024"],"end":["12/31/2024"]} for k in headers}
        alpha["2"]["begin"].append("01/07/2024")
        alpha["3"]["state"]=["NJ"]
        alpha["4"]["begin"]=["07/01/2024"]
        r=assess(headers,puf,alpha,{"012345":{"NY":1}})
        self.assertEqual(r["candidate_states"],{"three_way_candidate":2,"alpha_missing_or_duplicate":1,"identity_conflict":1,"date_conflict":1})
        self.assertEqual(r["duplicate_period_pairs"],1)
        self.assertEqual(r["nonconflicting_three_way_candidate_reports"],0)
    def test_form_specific_coordinates(self):
        self.assertEqual(FIELDS["hospital"]["begin"],("S200001","02000","00100"))
        self.assertEqual(FIELDS["snf"]["begin"],("S200001","01400","00100"))
