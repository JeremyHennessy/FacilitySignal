import csv,sqlite3,tempfile,unittest
from pathlib import Path
from collect_ownership import ORG,project,init,ingest,audit_linkage
class OwnershipTests(unittest.TestCase):
    def test_individual_never_projected(self):
        row={"TYPE - OWNER":"I","FIRST NAME - OWNER":"DO NOT RETAIN"}
        self.assertIsNone(project("owner",row))
        with self.assertRaises(ValueError):project("owner",{"TYPE - OWNER":"?"})
    def test_org_projection_and_failed_count_rollback(self):
        row={k:"" for k in ORG}
        row.update({"TYPE - OWNER":"O","ENROLLMENT ID":"O20070222000526","ASSOCIATE ID":"0012345678","ASSOCIATE ID - OWNER":"0001234567","ORGANIZATION NAME - OWNER":"Fixture LLC","FIRST NAME - OWNER":"DO NOT RETAIN"})
        p=project("owner",row)
        self.assertEqual(p[1],"0012345678");self.assertNotIn("DO NOT RETAIN",str(p))
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"test.csv"
            with path.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerow(row);w.writerow(dict(row,**{"TYPE - OWNER":"I"}))
            db=sqlite3.connect(":memory:");init(db)
            m={"zipped":False,"period":"fixture","modified":"fixture","api":"fixture","url":"fixture"}
            with self.assertRaisesRegex(ValueError,"count reconciliation"):ingest(db,"hospital-owner",m,path,"fixture",3)
            self.assertEqual(db.execute("SELECT count(*) FROM pecos_releases").fetchone()[0],0)
            a=ingest(db,"hospital-owner",m,path,"fixture",2)
            self.assertEqual((a["stored_rows"],a["excluded_individual_rows"]),(1,1))
            self.assertNotIn("DO NOT RETAIN",str(db.execute("SELECT * FROM pecos_org_role_rows").fetchall()))
            db.close()
