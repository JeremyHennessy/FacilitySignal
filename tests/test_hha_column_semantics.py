import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

class HHAColumnSemanticsTests(unittest.TestCase):
    def test_all_ordinals_reconcile_with_pinned_source(self):
        audit = read("research/hha_column_semantics_20261126.json")
        profile = next(s for s in read(audit["profile_path"])["sources"] if s["source"] == "home-health")
        lock = next(s for s in read("research/snapshot_release_20261125.json")["sources"] if s["key"] == "home-health")
        self.assertEqual(audit["source_sha256"], profile["source_sha256"])
        self.assertEqual(audit["source_sha256"], lock["sha256"])
        self.assertEqual(audit["release"], lock["release"])
        self.assertEqual(len(audit["fields"]), 96)
        self.assertEqual(audit["totals"]["retained_rows"], lock["stored_rows"])
        for a, p in zip(audit["fields"], profile["fields"]):
            self.assertEqual((a["ordinal"], a["field"]), (p["ordinal"], p["field"]))
            self.assertEqual(a["profile_states"], p.get("states"))
            self.assertEqual(a["restricted_presence"], p.get("presence"))
            self.assertEqual(a["lexical_shapes"], p.get("lexical_shapes"))
            self.assertEqual(a["distinct_nonmissing"], p.get("distinct_nonmissing"))
            self.assertEqual(a["existing_service_counts"], p.get("literal_yes_no_counts"))
            self.assertEqual(sum((a["profile_states"] or a["restricted_presence"]).values()), 12409)
            self.assertFalse(a["new_application_approval"])
            if a["number_shaped_rows"] is not None:
                shapes = p["lexical_shapes"]
                numeric = sum(shapes.get(k,0) for k in ("unsigned_integer_text","decimal_text","signed_integer_text"))
                self.assertEqual(a["number_shaped_rows"], numeric)
                self.assertEqual(numeric + a["unresolved_nonnumeric_rows"], 12409)

    def test_no_clinical_or_unknown_domain_promotion(self):
        a = read("research/hha_column_semantics_20261126.json")
        f = a["fields"]
        self.assertEqual([x["ordinal"] for x in f if x["application_disposition"] == "clinical_context_only"], list(range(16,97)))
        self.assertEqual([x["ordinal"] for x in f if x["application_disposition"] == "existing_narrow_projection_only"], list(range(9,15)))
        self.assertEqual([x["ordinal"] for x in f if x["restricted_presence"]], [7])
        self.assertEqual(a["totals"]["new_application_approved_fields"], 0)
        self.assertEqual(a["totals"]["new_domain_qualified_fields"], 0)
        self.assertEqual(f[15]["number_shaped_rows"], 8126)
        self.assertEqual(f[15]["unresolved_nonnumeric_rows"], 4283)
        self.assertEqual([f[i-1]["profile_states"]["not_available"] for i in (76,84,92)], [1710,3167,2095])
        self.assertEqual([x["ordinal"] for x in f if x["kind"] == "confidence_lower"], [74,82,90])
        self.assertEqual([x["ordinal"] for x in f if x["kind"] == "confidence_upper"], [75,83,91])
        self.assertIsNone(a["dictionary"]["retrieved_sha256"])

if __name__ == "__main__":
    unittest.main()
