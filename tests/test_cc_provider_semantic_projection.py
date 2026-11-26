import json,unittest
from pathlib import Path
from scripts.build_public_intelligence import build
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text(encoding="utf-8"))
class CCProviderSemanticProjectionTests(unittest.TestCase):
    def test_exact_selected_projection(self):
        obj=build(read("research/coverage_status.json"),read("research/public_capability_audit_20261126.json"),read("scripts/public_intelligence_spec.json"))
        self.assertEqual(obj,read("web/public-intelligence.json"))
        groups={g["id"]:g for s in obj["sections"] for g in s["groups"]}
        self.assertEqual(groups["cc-nursing-sprinkler"]["rows"],[["Yes",14599],["Partial",36],["No",0],["Data Not Available",51]])
        self.assertEqual(groups["cc-nursing-focus"]["rows"],[["Special Focus Facility",87],["Special Focus candidate",440],["No listed status (blank)",14159]])
        self.assertEqual(len(groups["cc-hospital-categories"]["rows"]),21)
        for field in ("Hospital Type","Hospital Ownership"):
            self.assertEqual(sum(r[2] for r in groups["cc-hospital-categories"]["rows"] if r[0]==field),5435)
        self.assertTrue(all(sum(r[1:])==5435 for r in groups["cc-hospital-quality-coverage"]["rows"]))
        self.assertIn(["Coordinates in range; footnote 22 (ZIP estimate)",808],groups["cc-nursing-location"]["rows"])
        self.assertIn(["Provider resides in hospital (Y)",608],groups["cc-nursing-location"]["rows"])
        self.assertEqual(len([k for k in groups if k.startswith("cc-")]),6)
    def test_source_field_coverage_and_limits(self):
        a=read("research/care_compare_provider_semantic_audit_20261126.json")
        self.assertEqual((a["field_count"],a["source_rows"]),(140,20121))
        self.assertEqual({s["source"]:s["columns"] for s in a["sources"]},{"hospital":38,"nursing":102})
        for s in a["sources"]:
            self.assertTrue(all(x["application_approval"]=="no_new_row_level_publication" for x in s["catalog"]))
            self.assertTrue(all(sum(v.values())==s["rows"] for v in s["distributions"].values()))
