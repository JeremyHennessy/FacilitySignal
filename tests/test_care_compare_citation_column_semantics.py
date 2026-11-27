import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
def read(path):
    return json.loads((ROOT / path).read_text())
def blob(path):
    data = (ROOT / path).read_bytes()
    return hashlib.sha1(("blob " + str(len(data)) + "\0").encode() + data).hexdigest()

class CitationColumnSemanticsTests(unittest.TestCase):
    def test_all_exact_headers_and_profiles(self):
        a = read("research/care_compare_citation_column_semantics_20261127.json")
        p = read(a["profile_path"])
        self.assertEqual(blob(a["profile_path"]), a["profile_blob"])
        self.assertEqual(a["prior_profile_run"], p["qualification_run"])
        profiles = {s["source"]: s for s in p["sources"]}
        lock = {s["key"]: s for s in read("research/snapshot_release_20261125.json")["sources"]}
        self.assertEqual({s["source"] for s in a["sources"]}, {"nursing-health", "nursing-fire"})
        for s in a["sources"]:
            k = s["source"]
            source = profiles[k]
            self.assertEqual((s["source_sha256"], s["release"], s["rows"]), (lock[k]["sha256"], lock[k]["release"], lock[k]["stored_rows"]))
            self.assertEqual(s["source_sha256"], source["source_sha256"])
            self.assertEqual(s["rows"], source["profiled_rows"])
            self.assertEqual(len(s["fields"]), 24)
            self.assertEqual([(f["ordinal"], f["field"]) for f in s["fields"]], [(f["ordinal"], f["field"]) for f in source["fields"]])
            for f, original in zip(s["fields"], source["fields"]):
                self.assertEqual(f["profile_states"], original["states"])
                self.assertEqual(f["distinct_nonmissing"], original["distinct_nonmissing"])
                self.assertEqual(f["lexical_shapes"], original["lexical_shapes"])
                self.assertEqual(sum(f["profile_states"].values()), s["rows"])
                self.assertTrue(f["meaning"])
                self.assertIs(f["new_application_approval"], False)
                self.assertIs(f["observed_code_domain_qualified"], False)
        self.assertEqual(sum(s["rows"] for s in a["sources"]), 619069)
        self.assertEqual(sum(len(s["fields"]) for s in a["sources"]), 48)

    def test_version_and_interpretation_boundaries(self):
        a = read("research/care_compare_citation_column_semantics_20261127.json")
        fields = {s["source"]: {f["field"]: f for f in s["fields"]} for s in a["sources"]}
        health, fire = fields["nursing-health"], fields["nursing-fire"]
        self.assertNotIn("Tag Version", health)
        self.assertNotIn("Survey Footnote", fire)
        self.assertEqual(health["Survey Footnote"]["dictionary_evidence"], "october_extracted_text_only")
        self.assertEqual(health["Survey Footnote"]["profile_states"], {"blank": 418488, "other_nonblank": 194})
        self.assertEqual(fire["Correction Date"]["profile_states"]["blank"], 1636)
        self.assertEqual(health["Correction Date"]["profile_states"]["blank"], 2610)
        self.assertEqual(fire["Tag Version"]["distinct_nonmissing"], {"count": 1, "method": "exact"})
        for scope in (health, fire):
            for flag in ("Citation under IDR", "Citation under IIDR"):
                self.assertEqual(scope[flag]["application_disposition"], "candidate_dispute_flag")
                self.assertEqual(scope[flag]["distinct_nonmissing"], {"count": 2, "method": "exact"})
                self.assertIs(scope[flag]["observed_code_domain_qualified"], False)
            self.assertEqual(scope["CMS Certification Number (CCN)"]["unit"], "text")
            self.assertEqual(scope["ZIP Code"]["unit"], "text")
        self.assertEqual(a["totals"]["new_application_approved_fields"], 0)
        self.assertEqual(a["totals"]["new_full_domain_qualified_fields"], 0)
        self.assertIsNone(a["dictionary"]["sha256"])

if __name__ == "__main__":
    unittest.main()
