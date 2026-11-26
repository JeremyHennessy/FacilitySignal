import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text())
class PecosSemanticProjectionTests(unittest.TestCase):
    def test_all_original_fields_have_definition_and_source(self):
        crosswalk=read("research/pecos_field_semantic_crosswalk_20261126.json")
        headers={s["source"]:s for s in read("research/care_compare_pecos_exact_headers_20261126.json")["sources"] if s["family"]=="pecos"}
        self.assertEqual(crosswalk["field_count"],186)
        self.assertEqual(set(headers),{s["source"] for s in crosswalk["sources"]})
        for s in crosswalk["sources"]:
            self.assertEqual([(f["ordinal"],f["field"]) for f in s["fields"]],[(f["ordinal"],f["field"]) for f in headers[s["source"]]["fields"]])
            self.assertTrue(all(f["meaning"] and f["publisher_dictionary"] and f["application_approval"]=="no_new_row_level_approval" for f in s["fields"]))
    def test_public_aggregate_counts_and_limits(self):
        groups={g["id"]:g for s in read("web/public-intelligence.json")["sections"] for g in s["groups"]}
        rows=groups["pecos-role-classes"]["rows"]
        self.assertEqual(sum(r[2] or 0 for r in rows),22735)
        self.assertEqual(sum(r[3] or 0 for r in rows),100231)
        self.assertEqual(groups["pecos-org-flags"]["rows"][0],["Management services",107,55,1453,331])
        self.assertEqual(groups["pecos-chow-types"]["rows"],[["AM","Acquisition / merger",116,2],["CH","Change of ownership",663,5338],["CO","Consolidation",0,0]])
        self.assertEqual(len(groups["hospital-enrollment-subgroups"]["rows"]),13)
        self.assertTrue(all(r[1]+r[2]==9120 for r in groups["hospital-enrollment-subgroups"]["rows"]))
    def test_no_individual_or_link_identifiers_in_new_projection(self):
        groups={g["id"]:g for s in read("web/public-intelligence.json")["sections"] for g in s["groups"]}
        for k in ("pecos-role-classes","pecos-org-flags","pecos-chow-types","hospital-enrollment-subgroups"):
            for r in groups[k]["rows"]:
                for v in r:
                    self.assertTrue(v is None or type(v) is int or isinstance(v,str))
                    if isinstance(v,str):
                        self.assertFalse(v.isdigit() and len(v)>=6)
