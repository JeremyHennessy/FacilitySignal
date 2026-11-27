import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text())
class DialysisColumnSemanticsTest(unittest.TestCase):
    def test_exact_source_and_profile_coverage(self):
        a=read("research/dialysis_column_semantics_20261126.json")
        p=next(x for x in read(a["profile_path"])["sources"] if x["source"]=="dialysis")
        lock=next(x for x in read("research/snapshot_release_20261125.json")["sources"] if x["key"]=="dialysis")
        self.assertEqual(a["source_sha256"],p["source_sha256"])
        self.assertEqual(a["source_sha256"],lock["sha256"])
        self.assertEqual(a["release"],lock["release"])
        self.assertEqual(a["rows"],7471)
        self.assertEqual(len(a["fields"]),146)
        for f,b in zip(a["fields"],p["fields"]):
            self.assertEqual((f["ordinal"],f["field"]),(b["ordinal"],b["field"]))
            self.assertEqual(f["profile_states"],b.get("states"))
            self.assertEqual(f["presence_only"],b.get("presence"))
            self.assertEqual(f["lexical_shapes"],b.get("lexical_shapes"))
            self.assertEqual(f["distinct_nonmissing"],b.get("distinct_nonmissing"))
            self.assertEqual(f["literal_yes_no_counts"],b.get("literal_yes_no_counts"))
            self.assertEqual(sum((f["profile_states"] or f["presence_only"]).values()),7471)
            self.assertFalse(f["new_application_approval"])
        self.assertEqual([f["ordinal"] for f in a["fields"] if f["presence_only"]],[13])
        self.assertEqual(a["totals"]["clinical_context_fields"],127)
        self.assertEqual(a["totals"]["institutional_context_fields"],18)
        self.assertEqual(a["totals"]["new_application_approved_fields"],0)
        self.assertEqual(a["totals"]["new_domain_qualified_fields"],0)
        self.assertIsNone(a["dictionary"]["sha256"])
    def test_retained_diagnostics_and_code_distributions(self):
        a=read("research/dialysis_column_semantics_20261126.json")
        prior=read(a["prior_clinical_evidence_path"])
        p=prior["sources"]["dialysis"]
        self.assertEqual(a["source_sha256"],p["sha256"])
        self.assertEqual(a["prior_clinical_run"],prior["qualification_run"])
        self.assertEqual(a["retained_clinical_cross_checks"],p["cross_checks"])
        codes=[f for f in a["fields"] if f["kind"]=="availability_code"]
        self.assertEqual(len(codes),24)
        self.assertEqual({f["field"] for f in codes},set(p["field_counts"]))
        for f in codes:
            self.assertEqual(f["observed_availability_code_counts"],p["field_counts"][f["field"]])
            self.assertEqual(sum(f["observed_availability_code_counts"].values()),7471)
            self.assertTrue(set(f["observed_availability_code_counts"])<=set(a["availability_codes"]["provisional_meanings"]))
        self.assertEqual(p["cross_checks"]["Five Star | availability"]["281 | numeric"],2695)
        self.assertEqual(p["cross_checks"]["Five Star | availability"]["281 | blank"],86)
        self.assertEqual(p["cross_checks"]["Standard Infection Ratio | confidence interval"]["ordered_and_contains_estimate"],4269)
        self.assertEqual(p["cross_checks"]["Hospitalization Rate (Facility) | confidence interval"]["ordered_and_contains_estimate"],7266)
