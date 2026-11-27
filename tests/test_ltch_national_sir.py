import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts import qualify_ltch_national_sir as q
from scripts.qualify_ltch_quality import SPECS

ROOT = Path(__file__).resolve().parents[1]


def dataset(rows, header=None):
    stream = io.StringIO(newline="")
    w = csv.writer(stream)
    w.writerow(SPECS["national"][3] if header is None else header)
    w.writerows(rows)
    stream.seek(0)
    return stream


def national(code, value="0.75", footnote="-", ident="NATION", window=q.WINDOW):
    return [ident, code, value, footnote, *window]


class LTCHNationalSIR(TestCase):
    def setUp(self):
        self.codes = list(q.NATIONAL)
        self.rows = [national(code, value) for code, value in zip(self.codes, ("0.5", "1.0", "0.0"))]

    def test_exact_national_codes_keep_aggregate_not_score_values(self):
        rows = self.rows + [national("L_024_02_NATL_OBS_RATE", "999.99")]
        result = q.screen_national(dataset(rows), 4)
        self.assertEqual(result["sir_numeric_rows"], 3)
        self.assertEqual(result["sir_explicit_zero_rows"], 1)
        self.assertEqual(result["sir_scores_different_from_unity"], 2)
        self.assertEqual(result["other_national_rows_not_semantically_qualified"], 1)
        self.assertNotIn("999.99", str(result))
        self.assertNotIn("0.5", str(result))

    def test_duplicate_code_provider_grain_and_wrong_period_fail_closed(self):
        prefix = self.rows[:2]
        for row in (national(self.codes[0]),
                    national(self.codes[2], ident="012345"),
                    national(self.codes[2], window=("10/01/2024", "09/30/2025", "split")),
                    national(self.codes[2], window=("10/01/2023", "09/30/2024", "-")),
                    national("L_011_06_NATL_OBS_RATE")):
            with self.subTest(row=row), self.assertRaises(ValueError):
                q.screen_national(dataset(prefix + [row]), 3)

    def test_invalid_national_scores_are_not_numeric_zero(self):
        for token in ("Not Available", "Not Applicable", "N/A", "-", "No", "1e1", "-1", "NaN", "Infinity"):
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, "score domain"):
                q.screen_national(dataset(self.rows[:2] + [national(self.codes[2], token)]), 3)
        with self.assertRaisesRegex(ValueError, "score domain"):
            q.screen_national(dataset(self.rows[:2] + [national(self.codes[2], "0", "6")]), 3)

    def test_provider_scalar_excludes_comparison_counts_and_ci(self):
        for code in ("L_006_01_COMP_PERF", "L_006_01_NUMERATOR", "L_006_01_ELIGCASES",
                     "L_006_01_CI_LOWER", self.codes[0], "UNRECOGNIZED"):
            with self.subTest(code=code):
                self.assertEqual(q.provider_score_state(code, "0", "-", q.WINDOW),
                                 "outside_provider_sir_scalar")
        self.assertEqual(q.provider_score_state("L_006_01_SIR", "0", "-",
                                                ("10/01/2024", "09/30/2025", "split")),
                         "window_unverified")

    def test_provider_unavailable_masked_and_zero_are_distinct(self):
        for score, footnote, expected in (
                ("Not Available", "6", "unavailable"),
                ("Not Applicable", "-", "not_applicable"),
                ("N/A", "-", "missing_or_ambiguous_token"),
                ("-", "-", "missing_or_ambiguous_token"),
                ("0.000", "6", "numeric_zero"),
                ("0", "-", "numeric_zero"),
                ("1.30", "-", "numeric_nonzero"),
                ("0", "2", "value_or_footnote_unverified"),
                ("0.1", "6", "value_or_footnote_unverified"),
                ("No", "-", "value_or_footnote_unverified")):
            with self.subTest(score=score, footnote=footnote):
                self.assertEqual(q.provider_score_state("L_006_01_SIR", score, footnote, q.WINDOW), expected)

    def test_cli_input_must_match_exact_bytes_and_retained_output_stays_aggregate(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "different.csv"
            path.write_bytes(b" " * 1787)
            with self.assertRaisesRegex(ValueError, "differ from retained receipt"):
                q.qualify(path)
        prior = json.loads(q.PIN.read_text())["audit"]["sources"]["national"]["publisher"]
        evidence = json.loads((ROOT / "research/fs042_ltch_national_sir_readiness_20261127.json").read_text())
        self.assertEqual((evidence["national_bytes"], evidence["national_sha256"]),
                         (prior["bytes"], prior["sha256"]))
        self.assertEqual((evidence["national_input_rows"], evidence["sir_numeric_rows"],
                          evidence["other_national_rows_not_semantically_qualified"]), (27, 3, 24))
        self.assertEqual((evidence["provider_observations_consumed"], evidence["row_level_retained"]), (0, 0))
        self.assertEqual(evidence["reuse_review"], "pending")
        self.assertFalse(evidence["public_promotion"])
