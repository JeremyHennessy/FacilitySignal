import json,hashlib,unittest
from pathlib import Path
from qualified_data_use import quantity,classify,OWNERSHIP,ROOT
class QualifiedDataUseTests(unittest.TestCase):
    def test_literal_states(self):
        self.assertEqual(quantity("0"),("0","reported_integer"))
        self.assertEqual(quantity(" 0012 "),("12","reported_integer"))
        self.assertEqual(quantity("Not Available"),("","not_available"))
        self.assertEqual(quantity("-1"),("","unrecognized"))
        self.assertEqual(classify("Proprietary",OWNERSHIP),"Proprietary")
        self.assertEqual(classify("not available",OWNERSHIP),"not_available")
        self.assertEqual(classify("Other label",OWNERSHIP),"unrecognized")
    def test_committed_enrichment(self):
        root=ROOT
        p=root/"research/qualified_data_use_20261126.json"
        if not p.exists():self.skipTest("Candidate generated evidence not yet present")
        e=json.loads(p.read_bytes())
        raw=(root/"web/public-directory/long-term-hospital.json").read_bytes()
        m=json.loads((root/"web/public-directory/manifest.json").read_bytes())["field_enrichments"]["long-term-hospital"]
        rows=json.loads(raw)["records"]
        self.assertEqual(hashlib.sha256(raw).hexdigest(),m["projection_sha256"])
        self.assertEqual(m["source_sha256"],e["ltch"]["source_sha256"])
        self.assertEqual(len(rows),311)
        known=[int(r["capacity"]) for r in rows if r["capacity"]!=""]
        self.assertEqual((len(known),sum(known),len(rows)-len(known)),(305,21765,6))
        self.assertEqual(sum(e["hha"]["ownership"].values()),12409)
        for v in e["hha"]["services"].values():
            self.assertEqual(v["yes"]+v["no"]+v["other_or_missing"],12409)
        for v in e["asc"]["services"].values():self.assertEqual(sum(v.values()),8492)
        self.assertEqual(e["audit"]["columns"],1433)
