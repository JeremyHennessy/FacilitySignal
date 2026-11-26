import json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import archive_qualified_data as q,azure_source_archive as s
class QualifiedDataArchiveTests(unittest.TestCase):
    def test_institutional_exact_domain(self):
        r={"fields":{"emergency_services":{"reported_yes":2,"reported_no":1}}}
        self.assertEqual(q.expected_literals("hospital",r),{"Emergency Services":{"Yes":2,"No":1}})
        r["fields"]["emergency_services"]["unexpected"]=1
        with self.assertRaises(ValueError):q.expected_literals("hospital",r)
    def test_new_namespaces(self):
        for key in ("institutional-field-observations","repository-data-evidence"):
            self.assertEqual(s.safe(s.prefix_for(key,"a"*64)+"/files/projection.sqlite3"),s.prefix_for(key,"a"*64)+"/files/projection.sqlite3")
            with self.assertRaises(ValueError):s.safe(s.prefix_for(key,"a"*64)+"/files/raw.csv")
    def test_exact_data_bytes_and_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/"research").mkdir()
            p=root/"research/test.json";p.write_bytes(b'{ "value": 1 }\n')
            r=q.a.rec("research/test.json",p)
            with patch.object(q,"ROOT",root):
                out,summary=q.build_data(None,{},root,[r],[r],[])
                self.assertEqual(summary["complete_manifest"],[r])
                with sqlite3.connect(out) as db:
                    self.assertEqual(db.execute("SELECT content FROM exact_data_files").fetchone()[0],p.read_bytes())
                p.write_bytes(b'{}')
                with self.assertRaises(Exception):q.build_data(None,{},root,[r],[r],[])
    def test_scope(self):
        for name in ("research/a.json","web/hcris-capacity/hospital.json","web/public-directory/nursing.json"):
            self.assertIsNotNone(q.DATA_PATH.fullmatch(name))
        for name in (".env","web/../credentials.json","data/raw.csv","research/a/b.json","web/index.html"):
            self.assertIsNone(q.DATA_PATH.fullmatch(name))
