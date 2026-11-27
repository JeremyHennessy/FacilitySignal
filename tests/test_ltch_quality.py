import csv
import io
import unittest
from scripts import qualify_ltch_quality as q

def data(kind, rows, header=None):
    f=io.StringIO()
    w=csv.writer(f)
    w.writerow(q.SPECS[kind][3] if header is None else header)
    w.writerows(rows)
    f.seek(0)
    return f

def provider(ident="012345", code="L_001", start="01/01/2025", end="12/31/2025"):
    return [ident,"Private fixture","Address","","City","AL","12345","County","phone","4",
            code,"0","-",start,end,"-"]

class LTCHQualityTests(unittest.TestCase):
    def test_provider_grain_and_missing(self):
        x=q.screen(data("provider",[provider(),provider(),provider("bad",start="",end="")]),"provider",3)
        self.assertEqual(x["provisional_distinct_keys"],1)
        self.assertEqual(x["repeated_key_rows"],1)
        self.assertEqual(x["unresolved_key_rows"],1)
        self.assertEqual(x["date_window_states"],{"ordered_explicit_dates":2,"missing_dates":1})
        self.assertEqual(x["field_presence"]["Score"],{"present":3})
        self.assertNotIn("012345",str(x))
        self.assertNotIn("Private fixture",str(x))
    def test_national_grain_and_reversed_dates(self):
        x=q.screen(data("national",[["NATION","L_001","Not Available","-","12/31/2025","01/01/2025","-"]]),"national",1)
        self.assertEqual(x["date_window_states"],{"unresolved_dates":1})
        self.assertEqual(x["field_presence"]["Score"],{"missing_literal":1})
        self.assertEqual(x["jurisdictions"],0)
    def test_strict_header_width_count(self):
        with self.assertRaisesRegex(ValueError,"header"):
            q.screen(data("provider",[provider()],["wrong"]),"provider",1)
        with self.assertRaisesRegex(ValueError,"width"):
            q.screen(data("provider",[provider()[:-1]]),"provider",1)
        with self.assertRaisesRegex(ValueError,"reconciliation"):
            q.screen(data("provider",[provider()]),"provider",2)
