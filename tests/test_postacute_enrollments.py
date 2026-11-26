import csv,sqlite3,tempfile,unittest
from pathlib import Path
from scripts import archive_postacute_enrollments as m

class PostacuteEnrollmentTests(unittest.TestCase):
    def test_institutional_projection_and_owner_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);reg=p/"nppes.db";own=p/"owners.db";out=p/"projection.db";source=p/"source.csv"
            with sqlite3.connect(reg) as db:
                db.execute("CREATE TABLE organization_fields(npi TEXT PRIMARY KEY,practice_state TEXT)")
                db.execute("INSERT INTO organization_fields VALUES('1234567893','NY')")
            with sqlite3.connect(own) as db:
                db.execute("CREATE TABLE pecos_org_role_rows(enrollment_id TEXT,pac_id TEXT)")
                db.execute("INSERT INTO pecos_org_role_rows VALUES('A12345678901234','1234567890')")
            cols=sorted(m.FIELDS|{"ORGANIZATION NAME","ADDRESS LINE 1"})
            def row(e,npi,code="00-06"):
                return {"ENROLLMENT ID":e,"ASSOCIATE ID":"1234567890","CCN":"123456","NPI":npi,"PROVIDER TYPE CODE":code,"STATE":"NY","ENROLLMENT STATE":"NY","ORGANIZATION NAME":"not retained","ADDRESS LINE 1":"not retained"}
            def write(rows):
                with source.open("w",newline="") as f:
                    w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
            t={**m.TARGETS["hha"],"owner_rows":1}
            write([row("A12345678901234","1234567893"),row("B12345678901234","invalid")])
            s=m.project(source,cols,2,t,reg,own,{"123456":{"NY"}},out)
            self.assertEqual(s["stored_rows"],1)
            self.assertEqual(s["missing_or_invalid_npi"],1)
            self.assertEqual(s["owner_exact_enrollment_pac"],1)
            self.assertEqual(s["care_compare_same_practice_state_ccn"],1)
            with sqlite3.connect(out) as db:
                self.assertEqual(db.execute("SELECT npi FROM enrollment_observations").fetchall(),[("1234567893",)])
                self.assertNotIn("ORGANIZATION NAME",str(db.execute("PRAGMA table_info(enrollment_observations)").fetchall()))
            write([row("A12345678901234","1234567893","00-08")])
            with self.assertRaises(Exception):m.project(source,cols,1,t,reg,own,{},p/"bad.db")
            write([row("A12345678901234","1234567893"),row("A12345678901234","1234567893")])
            with self.assertRaises(Exception):m.project(source,cols,2,t,reg,own,{},p/"dup.db")
