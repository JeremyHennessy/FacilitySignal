import unittest
from pecos_date_classification import dates,classify,audit
class Tests(unittest.TestCase):
    def test_formats(self):
        for v,s in [("12/31/2020","mdy_only"),("31/12/2020","dmy_only"),("01/02/2020","ambiguous_slash"),("02/02/2020","same_date_multiple_formats"),("02/30/2020","invalid_or_other"),("","blank")]:self.assertEqual(dates(v)[0],s)
    def test_labels(self):
        self.assertEqual(classify("00-09","PART A PROVIDER - HOSPITAL"),"00-09|matches")
        self.assertEqual(classify("00-09","wrong"),"00-09|label_differs")
        self.assertEqual(classify("99-99","wrong"),"unknown_code")
    def test_exclusion(self):
        r=audit("hospital-owner",[{"TYPE - OWNER":"I"},{"TYPE - OWNER":"O","ASSOCIATION DATE - OWNER":"12/31/2020"}])
        self.assertEqual(r["excluded_individual"],1)
        self.assertEqual(r["date_format_states"]["ASSOCIATION DATE - OWNER"],{"mdy_only":1})
