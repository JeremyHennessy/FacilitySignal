import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts import qualify_irf_payment_type as psf


DAY = date(2024, 9, 30)
START = date(2024, 1, 1)


def row(mac="12345", start=START, end=None, kind="50", waiver="N"):
    return mac, start, end, kind, waiver


class IrfPaymentTypeTest(unittest.TestCase):
    def test_termination_date_inclusive_and_later_end_does_not_revive_old(self):
        rows = [row(), row(start=date(2024, 2, 1), end=DAY)]
        self.assertEqual(psf.period_result(rows, DAY), "type_50_waiver_N")
        self.assertEqual(psf.period_result(rows, date(2024, 10, 1)), "no_unended_mac")

    def test_future_dates_do_not_participate(self):
        self.assertEqual(psf.period_result([row(start=date(2024, 10, 1))], DAY), "only_future_records")
        self.assertEqual(psf.period_result([row(kind="04"), row(start=date(2024, 10, 1))], DAY),
                         "type_04_waiver_N")

    def test_ambiguity_same_mac_tie_and_multi_mac_separate(self):
        self.assertEqual(psf.period_result([row(), row(kind="04")], DAY), "ambiguous_same_mac_latest")
        self.assertEqual(psf.period_result([row(), row(mac="88888")], DAY), "multiple_unended_macs_same_type")
        self.assertEqual(psf.period_result([row(), row(mac="88888", kind="04")], DAY),
                         "multiple_unended_macs_conflicting_types")

    def test_inverted_latest_is_not_silent_and_zero_dates_not_conflated(self):
        self.assertIsNone(psf.parse_date("00000000", termination=True))
        self.assertIs(psf.parse_date("00000000"), False)
        self.assertIs(psf.parse_date("20240230"), False)
        self.assertEqual(psf.period_result([row(), row(start=DAY, end=START)], DAY),
                         "invalid_latest_interval")
        self.assertEqual(psf.period_result([row(start=False)], DAY), "unresolved_effective_date")

    def test_exact_ccn_and_historical_type_are_separate_and_no_raw_retained(self):
        history = {"01TA20": [row(end=START, waiver="Y")], "010020": [row(kind="04")]}
        report = psf.cohort_summary({"01TA20", "01TB20"}, history)
        self.assertEqual(report["any_exact_psf_ccn"], 1)
        self.assertEqual(report["any_literal_type50_with_effective_date_by_extract"], 1)
        self.assertEqual(report["retrospective_checkpoint_counts"][DAY.isoformat()],
                         {"no_exact_ccn": 1, "no_unended_mac": 1})
        output = json.dumps(report)
        for value in ("01TA20", "01TB20", "12345"):
            self.assertNotIn(value, output)

    def test_wrong_archive_fails_before_data_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "archive.zip"
            bad.write_bytes(b"PK")
            with self.assertRaisesRegex(ValueError, "edition"):
                psf.pinned_psf(bad)
