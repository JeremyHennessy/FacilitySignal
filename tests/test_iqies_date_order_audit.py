import unittest
from scripts.audit_iqies_date_order import calendar_bucket

class IqiesDateOrderTests(unittest.TestCase):
    def test_calendar_conventions(self):
        cases={"12/31/2024":"mdy_only","31/12/2024":"dmy_only","01/02/2024":"both_different","2/2/2024":"both_same",
               "2/29/2024":"mdy_only","29/2/2024":"dmy_only","2/29/2023":"neither_valid","13/13/2024":"neither_valid",
               "00/01/2024":"neither_valid","1/1/0000":"neither_valid","Not Available":"not_available","  ":"blank",
               "2024-01-01":"other_shape","3/2/24":"other_shape"}
        for value,want in cases.items():
            with self.subTest(value=value):self.assertEqual(calendar_bucket(value),want)
