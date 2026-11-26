import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text())
class HospitalColumnSemanticsTest(unittest.TestCase):
    def test_all_fields_match_pinned_profile(self):
        a=read("research/hospital_column_semantics_20261126.json")
        p=next(x for x in read(a["profile_path"])["sources"] if x["source"]=="hospital")
        lock=next(x for x in read("research/snapshot_release_20261125.json")["sources"] if x["key"]=="hospital")
        self.assertEqual(a["source_sha256"],p["source_sha256"])
        self.assertEqual(a["source_sha256"],lock["sha256"])
        self.assertEqual(a["release"],lock["release"])
        self.assertEqual(a["rows"],5435)
        self.assertEqual(len(a["fields"]),38)
        for f,b in zip(a["fields"],p["fields"]):
            self.assertEqual((f["ordinal"],f["field"]),(b["ordinal"],b["field"]))
            self.assertEqual(f["profile_states"],b.get("states"))
            self.assertEqual(f["presence_only"],b.get("presence"))
            self.assertEqual(f["lexical_shapes"],b.get("lexical_shapes"))
            self.assertEqual(f["distinct_nonmissing"],b.get("distinct_nonmissing"))
            self.assertEqual(f["literal_yes_no_counts"],b.get("literal_yes_no_counts"))
            self.assertEqual(sum((f["profile_states"] or f["presence_only"]).values()),5435)
            self.assertFalse(f["new_application_approval"])
        self.assertEqual([f["ordinal"] for f in a["fields"] if f["application_disposition"]=="clinical_context_only"],list(range(13,39)))
        self.assertEqual([f["ordinal"] for f in a["fields"] if f["presence_only"]],[8])
        self.assertEqual(a["fields"][10]["literal_yes_no_counts"],{"yes":4501,"no":934})
        self.assertEqual(a["fields"][11]["profile_states"],{"blank":3193,"other_nonblank":2242})
        self.assertEqual(a["fields"][12]["profile_states"],{"not_available":2269,"other_nonblank":3166})
        self.assertEqual(a["totals"]["new_application_approved_fields"],0)
        self.assertIsNone(a["dictionary"]["sha256"])
    def test_existing_clinical_diagnostics_and_measure_scope(self):
        a=read("research/hospital_column_semantics_20261126.json")
        prior=read(a["prior_clinical_evidence_path"])
        self.assertEqual(a["prior_clinical_run"],prior["qualification_run"])
        self.assertEqual(a["source_sha256"],prior["sources"]["hospital"]["sha256"])
        self.assertEqual(a["retained_clinical_cross_checks"],prior["sources"]["hospital"]["cross_checks"])
        self.assertEqual(sum(a["methodology"]["group_sizes"].values()),52)
        for name in ("MORT","Safety","READM","Pt Exp","TE"):
            check=a["retained_clinical_cross_checks"][name+" Group Measure Count | count comparison"]
            self.assertEqual(sum(check.values()),5435)
            self.assertEqual(set(check),{"facility_count_within_group","incomplete_or_nonnumeric"})
