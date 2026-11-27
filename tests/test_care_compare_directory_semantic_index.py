import hashlib
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text())
def blob(p):
    data=(ROOT/p).read_bytes()
    return hashlib.sha1(("blob "+str(len(data))+"\0").encode()+data).hexdigest()
class DirectorySemanticIndexTests(unittest.TestCase):
    def test_all_seven_directory_review_pins(self):
        a=read("research/care_compare_directory_semantic_index_20261127.json")
        self.assertEqual(a["profile_blob"],blob(a["profile_path"]))
        self.assertEqual(a["national_index_blob"],blob(a["national_index_path"]))
        profile={s["source"]:s for s in read(a["profile_path"])["sources"]}
        lock={s["key"]:s for s in read("research/snapshot_release_20261125.json")["sources"]}
        self.assertEqual({s["source"] for s in a["sources"]},set(profile))
        self.assertEqual(len(a["sources"]),7)
        for s in a["sources"]:
            k=s["source"];o=read(s["evidence_path"]);o=next(x for x in o["sources"] if x["source"]==k) if "sources" in o else o
            self.assertEqual(s["evidence_blob"],blob(s["evidence_path"]))
            self.assertEqual(s["source_sha256"],o["source_sha256"])
            self.assertEqual(s["source_sha256"],lock[k]["sha256"])
            self.assertEqual(s["release"],lock[k]["release"])
            self.assertEqual(s["rows"],lock[k]["stored_rows"])
            self.assertEqual(s["columns"],len(o["fields"]))
            self.assertEqual(s["semantic_reviewed_fields"],len(o["fields"]))
            self.assertEqual([(f["ordinal"],f["field"]) for f in o["fields"]],[(f["ordinal"],f["field"]) for f in profile[k]["fields"]])
            self.assertTrue(all(f["new_application_approval"] is False for f in o["fields"]))
            self.assertEqual(s["restricted_presence_only_fields"],sum(bool(f.get("presence_only") or f.get("restricted_presence")) for f in o["fields"]))
            self.assertEqual(s["qualification"],"definition_reviewed_not_full_domain_qualification")
        self.assertEqual(sum(s["rows"] for s in a["sources"]),48004)
        self.assertEqual(sum(s["columns"] for s in a["sources"]),419)
        self.assertEqual(sum(s["restricted_presence_only_fields"] for s in a["sources"]),7)
        self.assertEqual(a["totals"]["aggregate_value_profile_fields"],412)
        self.assertEqual(a["totals"]["new_application_approved_fields"],0)
        self.assertEqual(a["totals"]["original_national_columns_outside_directory_review"],1014)
