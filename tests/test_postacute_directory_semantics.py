import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
def read(p): return json.loads((ROOT/p).read_text(encoding="utf-8"))

class PostacuteDirectorySemanticsTests(unittest.TestCase):
    def test_pinned_fields_and_profiles(self):
        a=read("research/postacute_directory_semantics_20261126.json")
        profiles={s["source"]:s for s in read(a["profile_path"])["sources"]}
        pins={s["key"]:s for s in read("research/snapshot_release_20261125.json")["sources"]}
        self.assertEqual({s["source"] for s in a["sources"]},{"hospice","long-term-hospital","rehabilitation"})
        self.assertEqual(sum(s["rows"] for s in a["sources"]),8003)
        self.assertEqual(sum(len(s["fields"]) for s in a["sources"]),37)
        for s in a["sources"]:
            p=profiles[s["source"]]; l=pins[s["source"]]
            self.assertEqual((s["source_sha256"],s["release"],s["rows"]),(l["sha256"],l["release"],l["stored_rows"]))
            self.assertEqual(s["source_sha256"],p["source_sha256"])
            self.assertEqual(len(s["fields"]),len(p["fields"]))
            for f,r in zip(s["fields"],p["fields"]):
                self.assertEqual((f["ordinal"],f["field"]),(r["ordinal"],r["field"]))
                for k, rk in (("profile_states","states"),("restricted_presence","presence"),("lexical_shapes","lexical_shapes"),("distinct_nonmissing","distinct_nonmissing")):
                    self.assertEqual(f[k],r.get(rk))
                self.assertEqual(sum((f["profile_states"] or f["restricted_presence"]).values()),s["rows"])
                self.assertFalse(f["new_application_approval"])
            self.assertEqual([f["ordinal"] for f in s["fields"] if f["restricted_presence"]],[9])
            self.assertIsNone(s["dictionary"]["sha256"])
    def test_scope_and_nonpromotion(self):
        a=read("research/postacute_directory_semantics_20261126.json")
        s={v["source"]:v for v in a["sources"]}
        self.assertIn("Tribal",s["long-term-hospital"]["fields"][10]["documented_domain"])
        self.assertNotIn("Tribal",s["rehabilitation"]["fields"][10]["documented_domain"])
        self.assertIn("Combination Government & Non-Profit",s["hospice"]["fields"][10]["documented_domain"])
        self.assertEqual(s["long-term-hospital"]["fields"][12]["unit"],"beds")
        self.assertEqual(a["totals"]["new_domain_qualified_fields"],0)
        self.assertEqual(a["totals"]["new_application_approved_fields"],0)
