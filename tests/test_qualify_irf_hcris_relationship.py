import json
import tempfile
import unittest
from pathlib import Path

from scripts import qualify_irf_hcris_relationship as audit


def report(parent="010123", begin="10/01/2023", end="09/30/2024"):
    return parent, "1", begin, end


def fields(parent="010123", child="01T123", cert="12/31/2010"):
    return {"parent": [parent], "unit": [child], "unit_name": ["NOT RETAINED"],
            "unit_cbsa": ["00001"], "unit_certification_date": [cert]}


class HcrisIrfRelationshipTest(unittest.TestCase):
    def test_requires_explicit_same_report_and_exact_header_match(self):
        case = fields()
        self.assertEqual(audit.classify(report(), case, ["5"])[0], "literal_distinct_pair")
        for change, reason in [
            ({"parent": ["010333"]}, "parent_ccn_missing_duplicate_or_header_mismatch"),
            ({"parent": ["010123", "010123"]}, "parent_ccn_missing_duplicate_or_header_mismatch"),
            ({"unit": ["01T123", "01T123"]}, "duplicate_unit_ccn"),
            ({"unit": ["010123"]}, "invalid_or_nondistinct_ccn"),
        ]:
            self.assertEqual(audit.classify(report(), {**case, **change}, ["5"]), (reason, None))

    def test_preserves_explicit_extended_ccn_and_type_mismatch(self):
        case = fields(parent="012024", child="01TA24")
        label, pair = audit.classify(report("012024"), case, ["1"])
        self.assertEqual(label, "literal_distinct_pair")
        self.assertEqual(pair[5:], ("lettered_third_fourth", "provider_type_not_single_rehabilitation_5"))
        good = audit.classify(report("012024"), case, ["5"])[1]
        self.assertEqual(good[1], "01TA24")
        self.assertEqual(good[-1], "type5_and_report_companions_corroborated")
        later = audit.classify(report(), fields(cert="10/01/2024"), ["5"])[1]
        self.assertEqual(later[-1], "companion_or_certification_date_unresolved")
        self.assertEqual(audit.classify(report(begin="07/01/2023"), fields(), ["5"])[0],
                         "before_reviewed_worksheet_version")

    def test_candidate_cohorts_keep_duplicate_directory_rows_separate(self):
        keys = [{"ccn": "01T123", "state": "AL"}, {"ccn": "01TA24", "state": "AL"}]
        parents = [{"ccn": "010123", "state": "AL"}, {"ccn": "012024", "state": "AL"},
                   {"ccn": "012024", "state": "AL"}]
        scopes = audit.directory_cohorts(keys, parents)
        self.assertEqual([len(v) for v in scopes.values()], [2, 1])
        header = {"1": report("012024")}
        p = audit.report_summary(header, {"1": fields("012024", "01TA24")}, {"1": ["5"]}, scopes)
        self.assertEqual(p["candidate_comparisons"]["all_literal_identifier_candidates"]["outcomes"]
                         ["exact_pair_lettered_third_fourth"], 1)
        self.assertNotIn("exact_pair_lettered_third_fourth",
                         p["candidate_comparisons"]["single_same_state_directory_parent_candidates"]["outcomes"])

    def test_repeated_and_alternate_reports_are_not_silently_collapsed(self):
        headers = {"1": report(), "2": report(), "3": report("010888")}
        alpha = {"1": fields(), "2": fields(), "3": fields(parent="010888")}
        p = audit.report_summary(headers, alpha, {i: ["5"] for i in headers}, {"test": {"01T123": "010123"}})
        self.assertEqual(p["literal_pair_rows"], 3)
        self.assertEqual(p["literal_distinct_pairs"], 2)
        self.assertEqual(p["repeated_pair_keys"], 1)
        self.assertEqual(p["same_pair_same_period_observation_pairs"], 1)
        self.assertEqual(p["child_ccns_with_overlapping_periods_across_parents"], 1)
        self.assertEqual(p["candidate_comparisons"]["test"]["outcomes"]["exact_pair_with_alternative_parent"], 1)
        for forbidden in ("01T123", "010123", "010888", "NOT RETAINED"):
            self.assertNotIn(forbidden, json.dumps(p))

    def test_source_pin_rejects_other_zip_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "wrong.zip"
            p.write_bytes(b"PK")
            with self.assertRaisesRegex(ValueError, "edition"):
                audit.pinned(p)
