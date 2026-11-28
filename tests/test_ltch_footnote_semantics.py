import hashlib
import unittest
from scripts import audit_ltch_footnote_semantics as q

class LTCHFootnoteSemanticsTests(unittest.TestCase):
    def test_documented_codes(self):
        self.assertEqual(set(q.FOOTNOTES), set("12345678"))
        self.assertEqual(len(set(q.FOOTNOTES.values())), 8)
        for token, reason in q.FOOTNOTES.items():
            self.assertEqual(q.classify("Not Available", token, "provider"), ("missing_literal", reason))
        self.assertEqual(q.classify("0", "6", "provider"), ("present", "lower_confidence_limit_unavailable"))
        self.assertEqual(q.classify("0", "", "provider"), ("present", "no_reported_footnote"))
        self.assertEqual(q.classify("", "4", "provider"), ("blank", "publisher_suppression"))

    def test_unknowns_and_grain(self):
        for token in ("9", "1,2", "1.0", "01"):
            self.assertEqual(q.classify("5", token, "provider"), ("present", "unresolved_footnote"))
        self.assertEqual(q.classify("5", "1", "national"), ("present", "unexpected_national_footnote"))
        with self.assertRaises(ValueError):
            q.classify("5", "1", "other")

    def test_aggregate_reconciliation_and_pin(self):
        raw = b"Score,Footnote\n0,6\nNot Available,4\n5,\n"
        pin = {"columns": 2, "input_rows": 3,
               "publisher": {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
               "field_presence": {"Score": {"present": 2, "missing_literal": 1},
                                  "Footnote": {"present": 2, "blank": 1}}}
        result = q.audit_bytes(raw, "provider", pin)
        self.assertEqual(result["input_rows"], 3)
        self.assertEqual(result["score_footnote_states"]["missing_literal|publisher_suppression"], 1)
        self.assertEqual(result["retained_rows"], 0)
        with self.assertRaises(ValueError):
            q.audit_bytes(raw.replace(b"0,6", b"1,6"), "provider", pin)
        pin["field_presence"]["Score"] = {"present": 3}
        with self.assertRaises(ValueError):
            q.audit_bytes(raw, "provider", pin)
