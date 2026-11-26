import csv,io,sqlite3,tempfile,unittest
from pathlib import Path
from scripts import archive_postacute_sources as p
from scripts.qualify_hospital_cost import CORE
class PostacuteTests(unittest.TestCase):
    def test_hha_financial_report_key_scope(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);hcris=root/"detail.sqlite3"
            with sqlite3.connect(hcris) as db:db.execute("CREATE TABLE reports(report_key TEXT PRIMARY KEY)");db.execute("INSERT INTO reports VALUES('1')")
            fields=CORE+p.HHA_MEASURES+["HHA Name"];f=io.StringIO();w=csv.writer(f);w.writerow(fields)
            w.writerow(["1","012345","NY","2024-01-01","2024-12-31",*"12 20 4 2".split(),"SECRET NAME"])
            w.writerow(["2","012346","NY","2024-01-01","2024-12-31",*"12 20 4 2".split(),"SECRET NAME"])
            out=p.hha_cost_project(f.getvalue().encode(),2,fields,root/"projection.sqlite3",{"012345":{"NY"}},hcris)
            self.assertEqual(out["hcris_exact_report_key_candidates"],{"exact_report_key":1,"unmatched_report_key":1})
            self.assertEqual(out["projected_measure_count"],4)
            with sqlite3.connect(root/"projection.sqlite3") as db:self.assertNotIn("SECRET NAME",str(list(db.iterdump())))
