"""Cross-check field utilization routing against the pinned raw-profile index.

No source downloads, private reads, or public pack changes are needed.
Routing is a research disposition, not an application release approval.
"""
from collections import Counter
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "research"

def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

class FieldUtilizationReconciliationTests(unittest.TestCase):
    def test_exact_field_routing_and_dispositions(self):
        index = read("national_data_understanding_index_20261126.json")
        utilization = read("field_utilization_20261126.json")
        sources = {s["source"]: s for s in utilization["sources"]}
        self.assertEqual(len(sources), len(utilization["sources"]))
        self.assertEqual(set(sources), {s["source"] for s in index["sources"]})
        dispositions, surfaces = Counter(), Counter()
        for source in index["sources"]:
            routed = sources[source["source"]]
            self.assertEqual((routed["release"], routed["sha256"], routed["columns"]),
                             (source["release"], source["sha256"], source["columns"]))
            self.assertEqual(len(routed["fields"]), source["columns"])
            self.assertEqual([(f["ordinal"], f["field"]) for f in routed["fields"]],
                             [(f["ordinal"], f["field"]) for f in source["fields"]])
            for f, r in zip(source["fields"], routed["fields"]):
                self.assertEqual(r["prior_mapping"], f["existing_projection_20261126_baseline"])
                self.assertTrue(set(r["basis"]) <= set(utilization["evidence"]))
                self.assertEqual(f["application_approval"], "not_granted_by_this_audit")
                dispositions[r["disposition"]] += 1
                surfaces[r["surface"]] += 1
                if r["disposition"] == "no_observed_values":
                    self.assertTrue(f["all_blank"])
                    self.assertEqual(r["surface"], "no_observed_values")
                if f["all_blank"]:
                    self.assertIn(r["disposition"], ("no_observed_values", "restricted_review"))
                if f["semantic_status"].startswith("blocked"):
                    self.assertEqual(r["disposition"], "blocked_semantics")
                if f["profile"] == "contact_or_personal_presence_only":
                    self.assertEqual(r["disposition"], "restricted_review")
        self.assertEqual(sum(dispositions.values()), index["totals"]["columns"])
        self.assertEqual(dict(dispositions), utilization["counts"])
        self.assertEqual(dict(surfaces), utilization["surfaces"])

if __name__ == "__main__":
    unittest.main()
