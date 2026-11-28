import csv
import io
import unittest
from scripts import qualify_irf_national_benchmark as q

def row(code="I_006_01_NATL_SIR", score="0", foot="-", ident="Nation",
        start="10/01/2024", end="09/30/2025", split="-"):
    return [ident, code, score, foot, start, end, split]

def fixture(rows, header=q.HEADER):
    s = io.StringIO()
    w = csv.writer(s)
    w.writerow(header)
    w.writerows(rows)
    s.seek(0)
    return s

class IRFNationalBenchmarkTests(unittest.TestCase):
    def test_documented_domains(self):
        self.assertEqual(len(q.CODES), 27)
        self.assertEqual((len(q.COUNTS), len(q.RATES), len(q.RATIOS)), (12, 12, 3))
        rows = [row(code, "0") for code in q.CODES]
        out = q.screen(fixture(rows), 27)
        self.assertTrue(out["semantic_screen_pass"])
        self.assertEqual(out["measure_families"], {"rate": 12, "provider_count": 12, "ratio_or_index": 3})
        self.assertEqual(out["score_states"]["provider_count:reported_zero"], 12)
    def test_unknown_and_missing_distinct(self):
        out = q.screen(fixture([row("UNREVIEWED", "-"), row(score="Not Available")]), 2)
        self.assertEqual(out["unknown_code_rows"], 1)
        self.assertEqual(out["score_states"]["ratio_or_index:missing"], 1)
        self.assertFalse(out["semantic_screen_pass"])
    def test_invalid_domain_and_dates(self):
        out = q.screen(fixture([row("I_017_01_PPR_PD_N_TOO_SMALL", "1.5", "1"),
                                 row("I_011_05_NATL_OBS_RATE", "101", start="12/31/2025")]), 2)
        self.assertEqual(out["score_states"]["provider_count:unresolved_count"], 1)
        self.assertEqual(out["score_states"]["rate:unresolved_rate"], 1)
        self.assertEqual(out["window_states"]["unresolved"], 1)
        self.assertEqual(out["footnote_states"]["unreviewed_present"], 1)
    def test_structural_rejection(self):
        for rows, n, header in [([row(), row()], 2, q.HEADER), ([row(ident="123456")], 1, q.HEADER),
                                ([row()], 2, q.HEADER), ([row()], 1, ["wrong"])]:
            with self.assertRaises(ValueError):
                q.screen(fixture(rows, header), n)
