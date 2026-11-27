"""Reconcile the CLIA projection gap against pinned aggregate evidence."""
import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "research/clia_projection_gap_domain_review_20261127.json"
SECTIONS = {
    "bounded_code_domain_counts": "code_counts",
    "literal_flag_counts": "literal_flag_counts",
    "conservative_date_states": "date_states",
    "quantity_states": "quantity_states",
    "reference_shape_counts": "reference_shape_counts"
}
EXPECTED = {
    "quantity_state_review": 8,
    "date_state_review": 13,
    "literal_flag_domain_reconciled": 15,
    "lexical_only": 13,
    "reference_shape_only": 10,
    "contact_excluded": 2,
    "unmapped_code_review": 3,
    "historical_code_domain_reconciled": 25
}

def classify(category, section, buckets):
    if category == "restricted_contact":
        return "contact_excluded"
    if section == "code_counts":
        return ("historical_code_domain_reconciled"
                if all(k == "blank" or k.startswith("code_") for k in buckets)
                else "unmapped_code_review")
    if section == "literal_flag_counts":
        return ("literal_flag_domain_reconciled"
                if set(buckets) <= {"blank", "literal_Y", "literal_N"}
                else "flag_review")
    return {"date_states": "date_state_review",
            "quantity_states": "quantity_state_review",
            "reference_shape_counts": "reference_shape_only"}.get(section, "lexical_only")

class CliaProjectionGapDomainReview(unittest.TestCase):
    def test_exact_evidence_partition(self):
        receipt = json.loads(RECEIPT.read_text())
        evidence = {}
        for path, expected in receipt["pinned_evidence"].items():
            raw = (ROOT / path).read_bytes()
            self.assertEqual(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(), expected)
            evidence[Path(path).stem] = json.loads(raw)
        source = next(s for s in evidence["national_data_understanding_index_20261126"]["sources"] if s["source"] == "clia")
        profile = evidence["clia_raw_field_profile_20261126"]
        dictionary = evidence["clia_historical_dictionary_crosswalk_20261126"]
        audit = evidence["clia_certificate_semantic_audit_20261126"]
        for obj in (profile, dictionary, audit):
            self.assertEqual(obj["source_sha256"], source["sha256"])
        self.assertEqual(receipt["source_sha256"], source["sha256"])
        self.assertEqual(receipt["source_rows"], profile["rows"])
        self.assertEqual(source["profiled_rows"], profile["rows"])
        self.assertEqual(audit["source_rows"], profile["rows"])
        for seq in (source["fields"], profile["fields"], dictionary["fields"], audit["catalog"]):
            self.assertEqual(len(seq), 103)
        actual = []
        for f, p, d, c in zip(source["fields"], profile["fields"], dictionary["fields"], audit["catalog"]):
            for other in (p, d, c):
                self.assertEqual((f["ordinal"], f["field"]), (other["ordinal"], other["field"]))
            self.assertEqual(sum(p["states"].values()), profile["rows"])
            if (f["existing_projection_20261126_baseline"] is not None or f["all_blank"]
                    or f["distinct"] is None or not f["other_nonmissing_or_present"]):
                continue
            self.assertEqual(d["distinct_candidate_definitions"], 1)
            self.assertEqual(p["states"]["other_nonblank"], f["other_nonmissing_or_present"])
            section = SECTIONS.get(c["actual_review"])
            buckets = audit[section][f["field"]] if section else {}
            if section:
                self.assertEqual(sum(buckets.values()), profile["rows"])
                self.assertEqual(buckets.get("blank", 0), f["blank"])
                self.assertTrue(all(isinstance(v, int) and v >= 0 for v in buckets.values()))
            actual.append(dict(ordinal=f["ordinal"], field=f["field"], category=c["category"],
                               nonblank=f["other_nonmissing_or_present"], evidence_section=section,
                               disposition=classify(c["category"], section, buckets),
                               application_approval="not_granted"))
        self.assertEqual(len(actual), 89)
        self.assertEqual(actual, receipt["fields"])
        self.assertEqual(Counter(x["disposition"] for x in actual), EXPECTED)
        self.assertEqual(receipt["counts"], EXPECTED)

    def test_negative_controls(self):
        self.assertEqual(classify("coded_classification", "code_counts", {"unmapped_code_95": 1}), "unmapped_code_review")
        self.assertEqual(classify("indicator", "literal_flag_counts", {"unexpected": 1}), "flag_review")
        self.assertEqual(classify("restricted_contact", None, {}), "contact_excluded")
        self.assertEqual(classify("reference", "reference_shape_counts", {"clia_shaped": 1}), "reference_shape_only")
