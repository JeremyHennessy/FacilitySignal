import json
import unittest
from probe_pos_fields import INVENTORY,verify_inventory,reconcile,docs_for

class PosFieldTests(unittest.TestCase):
    def test_exact_inventory(self):
        obj=verify_inventory(json.loads(INVENTORY.read_text()))
        self.assertEqual(sum(len(v["fields"]) for v in obj["registries"].values()),762)
        self.assertEqual(sum(v["source_rows"] for v in obj["registries"].values()),799990)
    def test_schema_not_values(self):
        r=reconcile([{"field":"CCN"},{"field":"STATE"}],[{"ccn":"private example","state":"NY"}])
        self.assertTrue(r["exact_normalized_schema"])
        self.assertNotIn("private example",str(r))
        self.assertFalse(reconcile([{"field":"CCN"}],[{"other":1}])["exact_normalized_schema"])
    def test_documentation_allowlist(self):
        r=docs_for({"references":["https://data.cms.gov/resources/pos","https://other.example/file"],"distribution":[{"format":"PDF","downloadURL":"https://data.cms.gov/file.pdf"}]})
        self.assertEqual(len(r),2)
