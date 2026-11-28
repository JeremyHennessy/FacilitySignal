import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import qualify_reh_op36 as reh


ROOT = Path(__file__).resolve().parents[1]


def encode(columns, rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


class RehOp36Test(unittest.TestCase):
    def setUp(self):
        common = dict(zip((*reh.MEASURE_FIELDS, *reh.START_END),
                          (reh.MEASURE, reh.MEASURE_NAME, *reh.PERIOD)))
        self.providers = [
            {**common, "Facility ID": f"{i:06d}", "State": "ZZ",
             "Facility Name": "MUST NOT EMIT", "Address": "MUST NOT EMIT",
             "Compared to National": reh.NA, "Footnote": "5",
             **dict.fromkeys(reh.VALUE_FIELDS, reh.NA)}
            for i in range(1, 50)
        ]
        self.providers[0].update({
            "Compared to National": "No Different than expected", "Footnote": "",
            "Denominator": "987", "Score": "23.45678", "Lower Estimate": "10", "Higher Estimate": "30",
        })
        self.providers[1].update({"Compared to National": "Number of cases too small", "Footnote": "1"})
        self.providers[2].update({"Footnote": "7"})
        self.national = {**common, "National Rate": reh.NA, "Footnote": "5",
                         **dict.fromkeys(reh.NATIONAL_COUNTS.values(), "0")}
        self.national["Number of Hospitals Same"] = "2"
        self.national["Number of Hospitals Too Few"] = "2"
        notes = {**reh.NOTE_TEXT, **{str(i): "synthetic" for i in range(10, 39)}}
        self.footnotes = [{"Footnote": k, "Footnote Text": v} for k, v in notes.items()]

    def report(self):
        return reh.qualify(encode(reh.PROVIDER_COLUMNS, self.providers),
                           encode(reh.NATIONAL_COLUMNS, [self.national]),
                           encode(reh.FOOTNOTE_COLUMNS, self.footnotes))

    def test_scope_and_unavailability_remain_separate(self):
        result = self.report()
        self.assertEqual(result["provider_export"]["status_counts"], {
            "reported_numeric": 1, "too_few": 1, "no_eligible_cases": 1, "period_result_unavailable": 46,
        })
        self.assertEqual(result["national_export"]["rate_status"], "period_result_unavailable")
        self.assertFalse(result["cross_grain_check"]["matches_published_national_comparison_counts"])
        self.assertEqual(result["cross_grain_check"]["difference_explanation"], "not established")
        self.assertEqual(result["application_clearance"], "pending")
        self.assertEqual(result["provider_rows_retained"], 0)
        self.assertEqual(result["provider_values_retained"], 0)
        for forbidden in ("MUST NOT EMIT", "000001", "23.45678"):
            self.assertNotIn(forbidden, json.dumps(result))

    def test_even_matching_counts_do_not_establish_coverage_population(self):
        self.national["Number of Hospitals Same"] = self.national["Number of Hospitals Too Few"] = "1"
        scope = self.report()["cross_grain_check"]
        self.assertTrue(scope["matches_published_national_comparison_counts"])
        self.assertFalse(scope["derivation_or_coverage_population_supported"])

    def test_reject_duplicate_identity_and_mixed_period(self):
        self.providers[-1]["Facility ID"] = self.providers[0]["Facility ID"]
        with self.assertRaisesRegex(ValueError, "identity"):
            self.report()
        self.providers[-1]["Facility ID"] = "000049"
        self.providers[-1]["Start Date"] = "01/01/2025"
        with self.assertRaisesRegex(ValueError, "period"):
            self.report()

    def test_reject_scores_on_unavailable_rows(self):
        self.providers[2]["Score"] = "0"
        with self.assertRaisesRegex(ValueError, "availability"):
            self.report()

    def test_reject_numeric_denominator_and_estimates_outside_model(self):
        self.providers[0]["Denominator"] = "0"
        with self.assertRaisesRegex(ValueError, "denominator"):
            self.report()
        self.providers[0].update({"Denominator": "987", "Lower Estimate": "100"})
        with self.assertRaisesRegex(ValueError, "envelope"):
            self.report()

    def test_reject_unknown_footnote_or_benchmark_promotion(self):
        self.footnotes[0]["Footnote Text"] = "Not the pinned definition"
        with self.assertRaisesRegex(ValueError, "crosswalk"):
            self.report()
        self.footnotes[0]["Footnote Text"] = reh.NOTE_TEXT["1"]
        self.national["National Rate"] = "0"
        with self.assertRaisesRegex(ValueError, "benchmark"):
            self.report()

    def test_entry_point_rejects_same_size_unpinned_data_quietly(self):
        with tempfile.TemporaryDirectory() as root:
            fake = Path(root) / "publisher.csv"
            fake.write_bytes(b"x" * reh.PINS["provider"][1])
            result = subprocess.run([sys.executable, str(ROOT / "scripts/qualify_reh_op36.py"),
                                     "--provider", str(fake), "--national", str(fake), "--footnotes", str(fake)],
                                    capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "REH OP-36 input verification failed; no receipt produced.\n")
