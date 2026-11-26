import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/"research"/p).read_text())
class Followup(unittest.TestCase):
    def test_institutional_evidence(self):
        a=read("institutional_observations_qualification_20261126.json")
        p={s["key"]:s for s in read("snapshot_release_20261125.json")["sources"]}
        self.assertEqual((a["source_records"],a["observations"],a["field_rules"]),(27592,101534,10))
        self.assertEqual(a["sqlite_integrity"],"ok")
        self.assertEqual(a["membership_and_state_filter_checks"],"passed")
        for k,v in a["sources"].items():
            self.assertEqual((v["source_sha256"],v["providers"]),(p[k]["sha256"],p[k]["stored_rows"]))
            self.assertEqual(v["observations"],v["providers"]*len(v["fields"]))
            self.assertTrue(all(sum(c.values())==v["providers"] for c in v["fields"].values()))
    def test_pecos_evidence(self):
        a=read("pecos_label_reconciliation_20261126.json")
        p=read("pecos_date_classification_qualification_20261126.json")["sources"]
        total=variants=0
        for k,v in a["sources"].items():
            self.assertEqual(v["sha256"],p[k]["sha256"])
            total+=v["rows"]
            for c in v["provider_code_label_states"].values():
                self.assertEqual(sum(c.values()),v["rows"])
                self.assertTrue(all(x.endswith(("|matches","|documented_general_dictionary_variant")) for x in c))
                variants+=sum(n for x,n in c.items() if x.endswith("|documented_general_dictionary_variant"))
        self.assertEqual((total,variants),(29640,62))
    def test_unresolved_registry_semantics(self):
        a=read("registry_semantic_conflict_followup_20261126.json")
        p=read("iqies_raw_field_profile_20261126.json")
        self.assertEqual(a["source_sha256"],p["source_sha256"])
        self.assertEqual(len(a["fields"]),5)
        for f in a["fields"]:
            self.assertIn("no promotion",f["release_gate"])
            self.assertEqual(sum(v["rows"] for v in f["all_scope_states"].values()),p["rows"])
            self.assertEqual(f["observed_scope_states"],f["all_scope_states"][f["scope"]])
