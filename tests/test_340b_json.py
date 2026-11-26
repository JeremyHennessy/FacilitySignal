import json,tempfile,unittest
from pathlib import Path
from scripts.qualify_340b_json import scan,report_page,URL
class HRSAJSONTests(unittest.TestCase):
    def test_top_level_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"r.json"
            p.write_text(json.dumps([{"340B ID":"SYN-001","CE ID":1,"Entity Type":"DSH","Participating":True,"Shipping Addresses":[{"CE ID":99,"Participating":False,"Address":"SECRET"}]}, {"340BId":"SYN-002","CeId":2,"EntityType":"CH","Participating":False}]))
            a=scan(p)
            self.assertEqual(a["stored_rows"],2)
            self.assertEqual(a["participation_counts"],{"publisher_true":1,"publisher_false":1})
            self.assertNotIn("SECRET",str(a));self.assertNotIn("SYN-001",str(a))
            p.write_text(json.dumps({"records":[{"CE ID":1}]}))
            self.assertEqual(scan(p)["stored_rows"],0)
    def test_scope(self):
        self.assertTrue(report_page(URL))
        self.assertFalse(report_page(URL.replace("/Reports/","/Login/")))
