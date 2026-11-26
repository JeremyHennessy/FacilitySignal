import unittest
from collections import Counter
from decimal import Decimal
from infrastructure_outliers import rank,summarize
class Tests(unittest.TestCase):
    def test_rank(self):
        self.assertEqual(rank([1,2,3,4],50),2)
        self.assertEqual(rank([1,2,3,4],99),4)
    def test_positive_only(self):
        r=summarize([Decimal(x) for x in [0,1,2,3]],Counter(zero=1,positive=3,blank=2))
        self.assertEqual(r["positive_p50"],"2")
        self.assertEqual(r["maximum_share_of_positive_sum"],"50.0000")
    def test_zero_and_missing(self):
        self.assertEqual(summarize([Decimal(0)],Counter(zero=1,blank=1)),{"states":{"zero":1,"blank":1},"positive_count":0})
    def test_reconciliation(self):
        with self.assertRaises(Exception):summarize([Decimal(1)],Counter())
