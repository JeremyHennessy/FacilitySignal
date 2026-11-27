"""QIES historical semantic candidate / lexical evidence audit; no application approval."""
import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "research/qies_projection_gap_lexical_review_20261127.json"
EXPECTED = {
    "numeric_lexical_candidate": 53,
    "integer_text_max_width_eight": 10,
    "text_or_code_unverified": 91,
    "historical_type_missing": 5,
    "historical_definition_conflict": 3,
}

def classify(s, p):
    if s["distinct_candidate_definitions"] != 1:
        return "historical_definition_conflict"
    t = s["definitions"][0]["type_candidate"]
    if not t:
        return "historical_type_missing"
    shapes = p["lexical_shapes"]
    count = p["states"]["other_nonblank"]
    if t == "NUMBER":
        return ("numeric_lexical_candidate"
                if shapes.get("unsigned_integer_text", 0) + shapes.get("decimal_text", 0) == count
                else "numeric_lexical_mismatch")
    if t == "DATE":
        return ("integer_text_max_width_eight"
                if shapes.get("unsigned_integer_text", 0) == count
                and p["max_nonmissing_trimmed_length"] == 8 else "date_lexical_review")
    if t in {"CHAR", "VARCHAR2"}:
        return "text_or_code_unverified"
    return "other_type_review"

class QIESProjectionGapLexicalReview(unittest.TestCase):
    def test_pinned_evidence_and_partition(self):
        receipt = json.loads(RECEIPT.read_text())
        evidence = {}
        for path, expected in receipt["pinned_evidence"].items():
            raw = (ROOT / path).read_bytes()
            self.assertEqual(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(), expected)
            evidence[Path(path).stem] = json.loads(raw)
        source = next(s for s in evidence["national_data_understanding_index_20261126"]["sources"]
                      if s["source"] == "qies")
        dictionary = evidence["qies_historical_dictionary_crosswalk_20261126"]
        profile = evidence["qies_raw_field_profile_20261126"]
        self.assertEqual(source["sha256"], receipt["source_sha256"])
        self.assertEqual(dictionary["source_sha256"], source["sha256"])
        self.assertEqual(profile["source_sha256"], source["sha256"])
        self.assertEqual(profile["rows"], receipt["source_rows"])
        self.assertEqual(source["profiled_rows"], profile["rows"])
        self.assertEqual(len(source["fields"]), 473)
        self.assertEqual(len(dictionary["fields"]), 473)
        self.assertEqual(len(profile["fields"]), 473)
        actual = []
        for f, s, p in zip(source["fields"], dictionary["fields"], profile["fields"]):
            self.assertEqual((s["ordinal"], s["field"]), (f["ordinal"], f["field"]))
            self.assertEqual((p["ordinal"], p["field"]), (f["ordinal"], f["field"]))
            self.assertEqual(sum(p["states"].values()), profile["rows"])
            if (f["existing_projection_20261126_baseline"] is not None or f["all_blank"]
                    or f["distinct"] is None or not f["other_nonmissing_or_present"]):
                continue
            self.assertEqual(sum(p["lexical_shapes"].values()), p["states"]["other_nonblank"])
            self.assertEqual(p["states"]["other_nonblank"], f["other_nonmissing_or_present"])
            self.assertFalse(p["scope_counts"])
            self.assertFalse(p["documented_code_counts"])
            self.assertFalse(p["numeric_aggregate_by_scope"])
            actual.append(dict(ordinal=f["ordinal"], field=f["field"], category=f["category"],
                               historical_types=list(dict.fromkeys(x["type_candidate"] for x in s["definitions"])),
                               historical_definition_count=s["distinct_candidate_definitions"],
                               nonblank=p["states"]["other_nonblank"], lexical_shapes=p["lexical_shapes"],
                               disposition=classify(s, p), application_approval="not_granted"))
        self.assertEqual(len(actual), 162)
        self.assertEqual(actual, receipt["fields"])
        self.assertEqual(Counter(x["disposition"] for x in actual), EXPECTED)
        self.assertEqual(receipt["counts"], EXPECTED)

    def test_negative_controls(self):
        d = {"distinct_candidate_definitions": 1, "definitions": [{"type_candidate": "NUMBER"}]}
        p = {"lexical_shapes": {"unsigned_integer_text": 1, "other_text": 1},
             "states": {"other_nonblank": 2}, "max_nonmissing_trimmed_length": 8}
        self.assertEqual(classify(d, p), "numeric_lexical_mismatch")
        d["definitions"][0]["type_candidate"] = "DATE"
        self.assertEqual(classify(d, p), "date_lexical_review")
        d["definitions"][0]["type_candidate"] = "CHAR"
        self.assertEqual(classify(d, p), "text_or_code_unverified")
        d["distinct_candidate_definitions"] = 2
        self.assertEqual(classify(d, p), "historical_definition_conflict")
