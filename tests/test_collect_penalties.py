import csv,io,sqlite3,unittest
from collect_penalties import HEADER,project,integer,iso
class PenaltyTests(unittest.TestCase):
    def test_projection(self):
        f=io.StringIO();w=csv.writer(f);w.writerow(HEADER)
        w.writerow(["012345","Example","Street","City","NY","10001","2025-01-01","Fine","123","1234","","","ignored","2025-02-01"])
        w.writerow(["012345","Example","Street","City","NY","10001","2025-01-01","Payment Denial","","","2025-01-02","42","ignored","2025-02-01"])
        w.writerow(["999999","Example","Street","City","CA","90001","2025-01-01","Fine","124","12.0","","","ignored","2025-02-01"])
        with sqlite3.connect(":memory:") as db:
            a=project(f.getvalue().encode(),3,db,{"012345":{"NY"}},"2025-03-01")
            self.assertEqual(a["stored_rows"],3);self.assertEqual(a["fine_amount_reported_sum_usd"],1246)
            self.assertEqual(a["link_counts"],{"same_state":2,"unmatched_ccn":1})
            self.assertEqual(a["field_anomalies"],{})
            self.assertNotIn("Example",str(a))
    def test_invalid_values(self):
        for s in ("1.2","-2","nan"):
            with self.assertRaises(ValueError):integer(s)
        with self.assertRaises(ValueError):iso("2025-02-30")
