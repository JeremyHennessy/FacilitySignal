import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import qualify_reh_op36 as op36
from scripts import qualify_reh_pecos as pecos
from scripts import qualify_reh_predecessors as pred


def archived(i, ccn, kind="00-09", state="AL", practice="AL"):
    return {
        "ENROLLMENT ID": f"EN{i:013d}", "CCN": ccn, "ENROLLMENT STATE": state,
        "STATE": practice, "PROVIDER TYPE CODE": kind, "PROVIDER TYPE TEXT": pred.TYPE_LABELS[kind],
    }


def later(i, ccn, former, date="02/01/2025"):
    return {**archived(i, ccn, pecos.REH_TYPE), "ASSOCIATE ID": "9876543210",
            "REH CONVERSION FLAG": "Y", "REH CONVERSION DATE": date, pred.FORMER: former}


def observation(ccn):
    return {
        "Facility ID": ccn, "State": "AL", "Measure ID": op36.MEASURE, "Measure Name": op36.MEASURE_NAME,
        "Start Date": op36.PERIOD[0], "End Date": op36.PERIOD[1], "Compared to National": op36.NA,
        "Footnote": "5", **dict.fromkeys(op36.VALUE_FIELDS, op36.NA),
    }


class RehPredecessorTest(unittest.TestCase):
    def test_preserve_exact_lettered_keys_and_multiple_predecessors(self):
        p = pred.compare([archived(1, "01U123"), archived(2, "010123", "00-85")],
                         [later(3, "010222", "01U123|010123")], [observation("010222")])
        self.assertEqual(p["cohort_later_typed_op36_ccns_with_reported_conversion_after_2024"], 1)
        self.assertEqual(p["cohort_later_current_ccns_present_in_historical_pecos"], 0)
        self.assertEqual(p["later_cases_by_number_of_qualified_former_ccns"], {2: 1})
        self.assertEqual(p["lettered_exact_former_ccn_occurrences"], 1)
        self.assertEqual(p["explicit_former_ccn_occurrences_by_outcome"]["historical_hospital_00_09"], 1)
        self.assertEqual(p["explicit_former_ccn_occurrences_by_outcome"]["historical_cah_00_85"], 1)
        for forbidden in ("01U123", "010123", "010222", "9876543210", "EN0000000000001", "02/01/2025"):
            self.assertNotIn(forbidden, json.dumps(p))

    def test_no_fallback_from_missing_former_or_similar_key(self):
        p = pred.compare([archived(1, "010123"), archived(2, "010222"), archived(3, "010333")],
                         [later(4, "010222", "01U123"), later(5, "010333", "")],
                         [observation("010222"), observation("010333")])
        self.assertEqual(p["cohort_later_current_ccns_present_in_historical_pecos"], 2)
        self.assertEqual(p["later_cases_by_number_of_qualified_former_ccns"], {0: 2})
        self.assertEqual(p["explicit_former_ccn_occurrences_by_outcome"]["not_in_archive"], 1)

    def test_candidates_with_multiple_rows_conflicting_state_or_reh_type_stay_unqualified(self):
        early = [archived(1, "010111"), archived(2, "010111", practice="CA"),
                 archived(3, "010222", practice=""), archived(4, "010333", "00-24")]
        p = pred.compare(early, [later(5, "010444", "010111|010222|010333")], [observation("010444")])
        for key in ("multiple_historical_enrollments", "state_conflict_or_missing", "historical_type_not_predecessor"):
            self.assertEqual(p["explicit_former_ccn_occurrences_by_outcome"][key], 1)
        self.assertEqual(p["distinct_qualified_former_ccns"], 0)

    def test_only_same_measure_cohort_and_reject_conflicting_later_state(self):
        p = pred.compare([archived(1, "010123")],
                         [later(2, "010222", "010123", "12/31/2024"), later(3, "010333", "010123"),
                          later(4, "010444", "010123", "")], [observation("010222"), observation("010444")])
        self.assertEqual(p["cohort_later_typed_op36_ccns_with_reported_conversion_after_2024"], 0)
        r = later(4, "010222", "010123")
        r["ENROLLMENT STATE"] = "TX"
        with self.assertRaisesRegex(ValueError, "state conflict"):
            pred.compare([archived(1, "010123")], [r], [observation("010222")])

    def test_bad_tokens_cannot_be_trimmed_normalized_or_deduplicated(self):
        for bad in ("01U123|", "01U123 |010123", "01u123", "01U123|01U123", "０10123", "01U123,010123"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "malformed"):
                pred.former_ccns(bad)

    def test_wrong_archive_bytes_quietly_fail_actual_entry_point(self):
        with tempfile.TemporaryDirectory() as root:
            fake = Path(root) / "bad.csv"
            fake.write_bytes(b"x" * pred.EARLY_SIZE)
            result = subprocess.run([sys.executable, "-m", "scripts.qualify_reh_predecessors",
                                     "--historical-enrollment", str(fake), "--later-enrollment", str(fake),
                                     "--op36-provider", str(fake)], capture_output=True, text=True, check=False,
                                    cwd=Path(__file__).resolve().parents[1])
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertEqual(result.stderr, "REH predecessor source verification failed; no receipt produced.\n")
