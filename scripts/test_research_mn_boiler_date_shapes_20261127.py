"""Synthetic tests plus pinned aggregate-header readback (no raw archive required)."""
import json
from pathlib import Path
import unittest
import research_mn_boiler_date_shapes_20261127 as d

class DateShapes(unittest.TestCase):
    def test_exact_pinned_header(self):
        root=Path(__file__).resolve().parents[1]
        header=json.loads((root/"research/mn_boiler_location_candidates_20261127.json").read_text())["dli_source"]["actual_header"]
        d.verify_header(header)
        for bad in (header[:-1], header+[header[-1]], list(reversed(header))):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                d.verify_header(bad)
    
    def test_calendar_and_unknown_shapes(self):
        self.assertEqual(d.parse_date(" 2/29/2024 ")[0], "parseable")
        self.assertEqual(d.parse_date("02/29/2025")[0], "invalid_calendar")
        self.assertEqual(d.parse_date("2026-02-30")[0], "invalid_calendar")
        self.assertEqual(d.parse_date("  "), ("missing", None))
        for raw in (None, 45519, "1900", "2026-11-27T00:00:00", "11/27/26"):
            with self.subTest(raw=raw):
                self.assertEqual(d.parse_date(raw), ("unsupported", None))
    
    def test_separate_and_no_legal_inference(self):
        def bucket(last, expiration):
            return d.date_buckets({"Last_Inspection_Date":last,"Expiration_Date":expiration})
        self.assertEqual(bucket("2025-04-04","11/27/2026"),("before_snapshot","on_snapshot_unresolved","last_before_expiration"))
        self.assertEqual(bucket("2026-11-28","2026-10-03"),("after_snapshot","before_snapshot","last_after_expiration"))
        self.assertEqual(bucket("2026-11-27","2026-11-27"),("on_snapshot","on_snapshot_unresolved","same_date"))
        self.assertEqual(bucket("","2027-01-01"),("missing","after_snapshot","not_comparable"))
    
if __name__=="__main__":
    unittest.main()
