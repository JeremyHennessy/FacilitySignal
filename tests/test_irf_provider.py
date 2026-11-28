import csv
import io
import unittest
from scripts import qualify_irf_provider as q

def fixture(rows, header=None):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(q.SPECS["provider"][3] if header is None else header)
    writer.writerows(rows)
    stream.seek(0)
    return stream

def row(ccn="012345", measure="I_006_01", score="0", start="01/01/2025", end="12/31/2025"):
    return [ccn, "Private fixture", "Address", "-", "City", "AL", "12345", "County",
            "phone", "4", measure, score, "-", start, end, "-"]

class IRFProviderTests(unittest.TestCase):
    def test_pin_and_scope(self):
        self.assertEqual(q.SPECS["provider"][:3], ("v9e4-nwhh", "2026-09-11", 79430))
        self.assertEqual(set(q.SPECS), {"provider"})
    def test_duplicate_missing_and_privacy(self):
        rows = [row(), row(), row("bad", score="Not Available", start="", end="")]
        out = q.screen(fixture(rows), "provider", 3)
        self.assertEqual(out["provisional_distinct_keys"], 1)
        self.assertEqual(out["repeated_key_rows"], 1)
        self.assertEqual(out["unresolved_key_rows"], 1)
        self.assertEqual(out["field_presence"]["Score"], {"present":2,"missing_literal":1})
        self.assertEqual(out["date_window_states"], {"ordered_explicit_dates":2,"missing_dates":1})
        self.assertNotIn("012345", str(out))
        self.assertNotIn("Private fixture", str(out))
    def test_drift(self):
        for stream, count in [(fixture([row()], ["wrong"]), 1),
                              (fixture([row()[:-1]]), 1),
                              (fixture([row()]), 2)]:
            with self.assertRaises(ValueError):
                q.screen(stream, "provider", count)
    def test_reversed_window(self):
        out = q.screen(fixture([row(start="12/31/2025", end="01/01/2025")]), "provider", 1)
        self.assertEqual(out["date_window_states"], {"unresolved_dates":1})
