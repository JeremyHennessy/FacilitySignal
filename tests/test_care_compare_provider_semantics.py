import unittest
from care_compare_provider_semantics import semantic,number_state,parsed_date,footnote,arithmetic,classify
class ProviderSemanticTests(unittest.TestCase):
    def test_unknown_is_not_zero(self):
        self.assertEqual(number_state("","count"),"blank")
        self.assertEqual(number_state("0","count"),"zero")
        self.assertEqual(number_state("0","rating"),"outside_1_5")
        self.assertEqual(number_state("2.5","rating"),"noninteger")
        self.assertEqual(number_state("110","percentage"),"above_100")
        self.assertEqual(classify("Partial","enum","Automatic Sprinkler Systems in All Required Areas","nursing"),"Partial")
    def test_footnotes_and_dates(self):
        self.assertEqual(footnote("22","nursing"),"code_22")
        self.assertEqual(footnote("29","nursing"),"code_29")
        self.assertEqual(footnote("95","nursing"),"unknown_numeric_code")
        self.assertEqual(footnote("95","hospital"),"code_95")
        self.assertEqual(parsed_date("11/12/2026")[0],"ambiguous_slash")
    def test_arithmetic(self):
        self.assertEqual(arithmetic({"t":"1.01","a":"0.5","b":"0.5"},"t",("a","b")),"within_display_precision")
        self.assertEqual(arithmetic({"t":"3","a":"1","b":"1"},"t",("a","b"),True),"reported_total_above_components")
        self.assertEqual(arithmetic({"t":"3","a":"","b":"1"},"t",("a","b")),"not_comparable")
    def test_field_scope(self):
        self.assertEqual(semantic("nursing","Telephone Number")[2],"presence")
        self.assertEqual(semantic("nursing","Overall Rating")[0],"clinical_quality_rating")
        self.assertEqual(semantic("nursing","Reported Total Nurse Staffing Hours per Resident per Day")[2],"decimal")
        self.assertEqual(semantic("hospital","Count of Facility MORT Measures")[0],"clinical_quality_coverage")
        with self.assertRaises(ValueError):semantic("hospital","unknown_field")
