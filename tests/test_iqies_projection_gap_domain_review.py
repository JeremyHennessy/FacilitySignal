"""Reconcile the original iQIES projection gap against pinned aggregate evidence.

No downloads, provider-level publication, or new application permissions.
"""
import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "research/iqies_projection_gap_domain_review_20261127.json"
EXPECTED = {
    "other_review": 19,
    "bounded_domain_mapped_code": 16,
    "scope_conflict": 20,
    "bounded_domain_boolean": 50,
    "bounded_domain_fte_decimal": 36,
    "bounded_domain_count_integer": 14,
    "blocked_metadata": 5,
    "domain_incomplete_mapped_code": 2,
    "domain_incomplete_fte_decimal": 2
}

def classify(semantic, profile):
    scopes = profile["scope_counts"]
    conflicts = sorted(k for k, v in scopes.items() if any(v.get(flag, 0) for flag in (
        "out_of_scope_nonblank", "scope_unresolved_nonblank", "applicability_conflict")))
    shape = semantic["interpretation_shape"]
    if semantic["semantic_review"].startswith("blocked"):
        return "blocked_metadata", conflicts
    if conflicts:
        return "scope_conflict", conflicts
    if shape not in {"boolean", "mapped_code", "count_integer", "fte_decimal"}:
        return "other_review", conflicts
    populated = [(k, v) for k, v in scopes.items() if v.get("other_nonblank", 0)]
    complete = bool(populated)
    for k, v in populated:
        n = v["other_nonblank"]
        if shape == "boolean":
            valid = v.get("reported_yes", 0) + v.get("reported_no", 0) == n
        elif shape == "mapped_code":
            valid = (v.get("documented_code", 0) == n and
                     sum(profile["documented_code_counts"].get(k, {}).values()) == n)
        else:
            valid = (v.get("nonnegative_numeric", 0) == n and
                     bool(profile["numeric_aggregate_by_scope"].get(k)))
        complete = complete and valid
    return ("bounded_domain_" if complete else "domain_incomplete_") + shape, conflicts

class IQIESProjectionGapReview(unittest.TestCase):
    def test_exact_pinned_evidence_and_partition(self):
        receipt = json.loads(RECEIPT.read_text())
        evidence = {}
        for path, expected in receipt["pinned_evidence"].items():
            raw = (ROOT / path).read_bytes()
            self.assertEqual(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(), expected)
            evidence[Path(path).stem] = json.loads(raw)
        index = evidence["national_data_understanding_index_20261126"]
        source = next(s for s in index["sources"] if s["source"] == "iqies")
        semantic = evidence["iqies_semantic_application_crosswalk_20261126"]["fields"]
        profile = evidence["iqies_raw_field_profile_20261126"]
        self.assertEqual(source["sha256"], profile["source_sha256"])
        self.assertEqual(receipt["source_sha256"], profile["source_sha256"])
        self.assertEqual(receipt["source_rows"], profile["rows"])
        self.assertEqual(len(semantic), 186)
        self.assertEqual(len(profile["fields"]), 186)
        actual = []
        for f in source["fields"]:
            s, p = semantic[f["ordinal"] - 1], profile["fields"][f["ordinal"] - 1]
            self.assertEqual((s["field"], s["ordinal"]), (f["field"], f["ordinal"]))
            self.assertEqual((p["field"], p["ordinal"]), (f["field"], f["ordinal"]))
            self.assertEqual(sum(v["rows"] for v in p["scope_counts"].values()), profile["rows"])
            if f["existing_projection_20261126_baseline"] is not None or f["all_blank"] or f["distinct"] is None or not f["other_nonmissing_or_present"]:
                continue
            disposition, conflicts = classify(s, p)
            actual.append(dict(ordinal=f["ordinal"], field=f["field"], category=s["category"], disposition=disposition, conflicting_scopes=conflicts, application_approval="not_granted"))
        self.assertEqual(len(actual), 164)
        self.assertEqual(actual, receipt["fields"])
        self.assertEqual(Counter(x["disposition"] for x in actual), EXPECTED)
        self.assertEqual(receipt["counts"], EXPECTED)

    def test_negative_controls(self):
        semantic = {"semantic_review": "reviewed", "interpretation_shape": "boolean"}
        profile = {"scope_counts": {"ASC": {"other_nonblank": 2, "reported_yes": 1, "reported_no": 1}}}
        self.assertEqual(classify(semantic, profile)[0], "bounded_domain_boolean")
        profile["scope_counts"]["ASC"]["reported_no"] = 0
        self.assertEqual(classify(semantic, profile)[0], "domain_incomplete_boolean")
        profile["scope_counts"]["ASC"]["applicability_conflict"] = 1
        self.assertEqual(classify(semantic, profile)[0], "scope_conflict")
        semantic["semantic_review"] = "blocked_dictionary"
        self.assertEqual(classify(semantic, profile)[0], "blocked_metadata")

if __name__ == "__main__":
    unittest.main()
