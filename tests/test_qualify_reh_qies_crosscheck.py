import json
import unittest

from scripts import qualify_reh_qies_crosscheck as qies


def row(c="010111", state="AL", subtype="28", cert="20241215", orig="20250110", term=""):
    return dict(zip(qies.COLUMNS, (c, state, "01", subtype, "", cert, orig, "00", term)))


class RehQiesCrosscheckTest(unittest.TestCase):
    def test_keeps_clocks_and_absent_lettered_keys_separate(self):
        p = qies.edition([row()], [row()], {"fixture": {"010111": "AL", "01U111": "AL"}})
        scope = p["fixture"]
        self.assertEqual(scope["lettered_ccns_not_returned"], 1)
        self.assertEqual(scope["typed_01_28_exact_matches"], 1)
        self.assertEqual(scope["typed_exact_matches_with_both_reported_dates_by_2024_end"], 0)
        self.assertEqual(scope["reported_certification_and_original_participation_dates_differ"], 1)
        self.assertEqual(scope["literal_date_buckets"], {
            "CRTFCTN_DT": {"on_or_before_2024_end": 1},
            "ORGNL_PRTCPTN_DT": {"after_2024_end": 1},
            "TRMNTN_EXPRTN_DT": {"blank": 1},
        })
        self.assertEqual(p["national_typed_general_type_blank"], 1)
        for key in ("010111", "01U111", "20241215", "20250110"):
            self.assertNotIn(key, json.dumps(p))

    def test_multiple_rows_and_conflicting_state_do_not_pass_exact_join(self):
        rows = [row(), row(state="TX"), row(c="010222", state="TX")]
        p = qies.edition(rows, rows, {"fixture": {"010111": "AL", "010222": "AL"}})["fixture"]
        self.assertEqual(p["match_outcomes"], {"exact_ccn_and_state": 0, "not_returned": 0,
                                               "multiple_exact_ccn_rows": 1, "state_conflict": 1})

    def test_two_exact_api_response_scopes_must_reconcile_counts_and_dates(self):
        scopes = {"fixture": {"010111": "AL"}}
        for typed in ([], [row(orig="20250201")]):
            with self.assertRaisesRegex(ValueError, "disagree"):
                qies.edition([row()], typed, scopes)
        with self.assertRaisesRegex(ValueError, "outside scope"):
            qies.edition([row(subtype="11")], [row(subtype="11")], scopes)

    def test_invalid_syntax_and_ambiguous_limit_fail_closed(self):
        for malformed in (row(cert="20240230"), row(c="10111"), row(state="Al")):
            with self.assertRaises(ValueError):
                qies.validate([malformed], {malformed["PRVDR_NUM"]})
        with self.assertRaisesRegex(ValueError, "truncated"):
            qies.validate([row()] * qies.MAX_ROWS)

    def test_distinguishes_literal_zero_date_from_blank_without_conclusion(self):
        r = row(cert="00000000")
        p = qies.summarise({"010111": "AL"}, qies.validate([r], {"010111"}))
        self.assertEqual(p["literal_date_buckets"]["CRTFCTN_DT"], {"literal_zero": 1})
        self.assertEqual(p["literal_date_buckets"]["TRMNTN_EXPRTN_DT"], {"blank": 1})
        self.assertEqual(p["reported_certification_and_original_participation_dates_differ"], 0)
