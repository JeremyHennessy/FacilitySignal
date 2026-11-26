import unittest
from clinical_measure_quality import numeric,code,footnote,interval,fraction
class Tests(unittest.TestCase):
    def test_code_preserves_zeros(self):
        self.assertEqual(code("001"),"001")
        self.assertEqual(code("1"),"1")
        self.assertEqual(code(""),"blank")
    def test_no_text_retention(self):
        self.assertEqual(footnote("2, 3"),"numeric_code_or_sequence")
        self.assertEqual(footnote("suppressed for any reason"),"text_or_other")
    def test_intervals(self):
        self.assertEqual(interval("1.2","0.8","1.4"),"ordered_and_contains_estimate")
        self.assertEqual(interval("1.2","0.8","1.0"),"ordered_estimate_outside")
        self.assertEqual(interval("1.2","2","1"),"reversed_bounds")
        self.assertEqual(interval("1.2","","1"),"incomplete_or_nonnumeric")
    def test_counts(self):
        self.assertEqual(fraction("0","0"),"zero_denominator")
        self.assertEqual(fraction("3","2"),"outside_count_relationship")
        self.assertEqual(fraction("1","2"),"nonnegative_numerator_within_positive_denominator")
