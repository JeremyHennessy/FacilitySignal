import json
import unittest
from scripts.public_identity_candidate_audit import audit, qualified

def record(ccn, address, state="NY", zip="10001"):
    return {"ccn": ccn, "address": address, "city": "New York", "state": state, "zip": zip}

def pack(source, records):
    return {"source": source, "row_count": len(records), "records": records}

class PublicIdentityAuditTests(unittest.TestCase):
    def test_candidate_states_and_no_merge(self):
        a = [record("001", "1 Main St"), record("002", "2 Main St"), record("003", ""), record("005", "1 Main St")]
        b = [record("001", "1  MAIN ST"), record("004", "2 Main St"), record("003", ""), record("005", "1 Main St", "NJ")]
        result = audit({"a": pack("a", a), "b": pack("b", b)})
        p = result["source_pairs"][0]
        self.assertEqual(p["same_ccn_candidates"], 3)
        self.assertEqual(p["same_ccn_same_state"], 2)
        self.assertEqual(p["same_ccn_conflicting_state"], 1)
        self.assertEqual(p["same_ccn_complete_address"], 1)
        self.assertEqual(p["same_ccn_incomplete_address"], 1)
        self.assertEqual(p["same_ccn_different_complete_address"], 1)
        self.assertEqual(p["same_address_distinct_ccn"], 2)
        self.assertEqual(p["union_candidate_pairs"], 5)
        self.assertEqual(result["sources"]["a"]["same_source_address_groups"], 1)
        self.assertEqual(result["canonical_merges"], 0)
    def test_no_implicit_zip_or_abbreviation_normalization(self):
        result = audit({"a": pack("a", [record("1", "1 Main St")]), "b": pack("b", [record("2", "1 Main Street"), record("3", "1 Main St", zip="10001-1234")])})
        self.assertEqual(result["source_pairs"][0]["same_address_pairs"], 0)
    def test_duplicate_source_identifier_rejected(self):
        with self.assertRaises(ValueError):
            audit({"a": pack("a", [record("001", "A"), record("001", "B")])})
    def test_actual_seven_pinned_public_directories(self):
        result = qualified()
        self.assertEqual(len(result["sources"]), 7)
        self.assertEqual(len(result["source_pairs"]), 21)
        self.assertEqual(result["provider_source_records"], sum(x["rows"] for x in result["source_pins"].values()))
        self.assertEqual(result["canonical_merges"], 0)
        print("FACILITYSIGNAL_PUBLIC_IDENTITY_AUDIT", json.dumps(result, sort_keys=True), flush=True)
