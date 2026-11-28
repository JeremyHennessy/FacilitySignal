import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import qualify_reh_op36 as op36
from scripts import qualify_reh_pecos as pecos


def enrollment(n, ccn, date=""):
    return {
        "ENROLLMENT ID": f"EN{n:013d}", "ASSOCIATE ID": "9876543210",
        "STATE": "AL", "ENROLLMENT STATE": "AL", "CCN": ccn,
        "PROVIDER TYPE CODE": pecos.REH_TYPE, "PROVIDER TYPE TEXT": pecos.REH_LABEL,
        "REH CONVERSION FLAG": "Y", "REH CONVERSION DATE": date,
    }


def measure(ccn):
    return {
        "Facility ID": ccn, "State": "AL", "Measure ID": op36.MEASURE, "Measure Name": op36.MEASURE_NAME,
        "Start Date": op36.PERIOD[0], "End Date": op36.PERIOD[1], "Compared to National": op36.NA,
        "Footnote": "5", **dict.fromkeys(op36.VALUE_FIELDS, op36.NA),
    }


class RehPecosTest(unittest.TestCase):
    def setUp(self):
        self.enrollments = [enrollment(1, "010111", "04/01/2026"), enrollment(2, "010222"),
                            enrollment(3, "010333", "12/31/2024"), enrollment(4, "010444")]
        self.enrollments[-1].update({"PROVIDER TYPE CODE": "00-09", "PROVIDER TYPE TEXT": pecos.OTHER_TYPES["00-09"]})
        self.measures = [measure("010111"), measure("010222"), measure("010333"), measure("010444")]

    def test_typed_source_only_same_suffix_is_not_proof(self):
        result = pecos.compare(self.enrollments, self.measures)
        self.assertEqual(result["all_enrollment_rows"], 4)
        self.assertEqual(result["typed_distinct_enrollment_ids"], 3)
        self.assertEqual(result["typed_distinct_pac_ids"], 1)
        self.assertEqual(result["typed_distinct_exact_ccns"], 3)
        self.assertEqual(result["op36_distinct_exact_ccns"], 4)
        self.assertEqual(result["both_sources_exact_ccn_both_states_agree"], 3)
        self.assertEqual(result["op36_only"], 1)
        self.assertEqual(result["typed_pecos_only"], 0)
        self.assertEqual(result["later_pecos_reported_conversion_date_by_match_scope"]["exact_matched"],
                         dict.fromkeys(pecos.BUCKETS, 1))
        self.assertEqual(result["application_clearance"], "pending")
        for forbidden in ("9876543210", "010111", "EN0000000000001", "04/01/2026"):
            self.assertNotIn(forbidden, json.dumps(result))

    def test_type_classified_only_from_exact_current_code_and_label(self):
        self.enrollments[-1]["PROVIDER TYPE TEXT"] = pecos.REH_LABEL
        with self.assertRaisesRegex(ValueError, "code/text"):
            pecos.compare(self.enrollments, self.measures)
        self.enrollments[0]["PROVIDER TYPE TEXT"] = pecos.OTHER_TYPES["00-09"]
        with self.assertRaisesRegex(ValueError, "code/text"):
            pecos.compare(self.enrollments, self.measures)

    def test_historical_and_later_states_do_not_silently_conflict(self):
        self.enrollments[0]["STATE"] = "TX"
        with self.assertRaisesRegex(ValueError, "conflicting state"):
            pecos.compare(self.enrollments, self.measures)
        self.enrollments[0]["STATE"] = "AL"
        self.enrollments[0]["ENROLLMENT STATE"] = "TX"
        with self.assertRaisesRegex(ValueError, "conflicting state"):
            pecos.compare(self.enrollments, self.measures)

    def test_exact_collision_distinct_specialties_is_ambiguous(self):
        self.enrollments[-1]["CCN"] = self.enrollments[0]["CCN"]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            pecos.compare(self.enrollments, self.measures)

    def test_duplicate_enrollment_or_historical_observation_fails_closed(self):
        self.measures.append(self.measures[-1].copy())
        with self.assertRaisesRegex(ValueError, "duplicate"):
            pecos.compare(self.enrollments, self.measures)
        self.enrollments[-1]["ENROLLMENT ID"] = self.enrollments[0]["ENROLLMENT ID"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            pecos.compare(self.enrollments, self.measures[:-1])

    def test_conversion_dates_calendar_and_cutoffs(self):
        self.assertEqual(pecos.date_bucket("12/31/2024"), pecos.BUCKETS[0])
        self.assertEqual(pecos.date_bucket("01/01/2025"), pecos.BUCKETS[1])
        self.assertEqual(pecos.date_bucket(""), pecos.BUCKETS[2])
        for unknown in ("00", "  ", "02/29/2025", "11/13/2026"):
            with self.subTest(unknown=unknown), self.assertRaises(ValueError):
                pecos.date_bucket(unknown)

    def test_pinned_entry_point_rejects_wrong_bytes_without_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            fake = Path(root) / "publisher.csv"
            fake.write_bytes(b"x" * pecos.ENROLL_PIN[0])
            result = subprocess.run([sys.executable, "-m", "scripts.qualify_reh_pecos",
                                     "--enrollment", str(fake), "--op36-provider", str(fake)],
                                    capture_output=True, text=True, check=False, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertEqual(result.stderr, "PECOS REH input verification failed; no receipt produced.\n")
