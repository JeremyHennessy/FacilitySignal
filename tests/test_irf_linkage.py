import csv
import io
import unittest
from scripts import qualify_irf_linkage as q

def payload(header, rows):
    buf=io.StringIO()
    writer=csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue().encode()

def common(token, state="AL", name="Synthetic"):
    return [token,name,"Address","-","City",state,"12345","County","-","4"]

def directory(token,state="AL",name="Synthetic"):
    return common(token,state,name)+["Other","01/01/2020"]

def provider(token,state="AL",name="Synthetic",code="M"):
    return common(token,state,name)+[code,"0","-","01/01/2025","12/31/2025","-"]

class IRFLinkageTests(unittest.TestCase):
    def test_documented_shapes(self):
        for token,kind in [("013025","numeric_rehab_range"),("013100","numeric_other_range"),
                           ("01R123","unit_R"),("01T123","unit_T"),("01TA12","extended_documented_marker_candidate"),
                           ("01TQ12","unresolved"),("01t123","unresolved"),(" 01T123","unresolved")]:
            self.assertEqual(q.shape(token),kind)
    def test_linkage_and_privacy(self):
        d=payload(q.DIRECTORY,[directory("013025"),directory("01T123"),directory("01R456")])
        p=payload(q.PROVIDER,[provider("013025"),provider("01T123"),provider("01T123","NY",code="N"),provider("01TA12")])
        out=q.screen(d,p,3,4)
        self.assertEqual(out["exact_token_intersection"],2)
        self.assertEqual(out["provider_link_states"],{"same_state_exact_context":1,"mixed_evidence":1,"unmatched_ccn":1})
        self.assertEqual(out["directory_only"],1)
        self.assertEqual(out["canonical_matches"],0)
        self.assertNotIn("01T123",str(out))
        self.assertNotIn("Synthetic",str(out))
    def test_duplicates_fail_closed(self):
        d=payload(q.DIRECTORY,[directory("01T123")])
        p=payload(q.PROVIDER,[provider("01T123"),provider("01T123")])
        with self.assertRaises(ValueError):
            q.screen(d,p,1,2)
        with self.assertRaises(ValueError):
            q.screen(d,p,2,2)
    def test_pins(self):
        self.assertEqual(q.pins()["directory"]["rows"],1222)
        self.assertEqual(q.pins()["provider"]["rows"],79430)
