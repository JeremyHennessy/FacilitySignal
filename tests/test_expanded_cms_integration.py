import hashlib,sqlite3,tempfile,unittest
from pathlib import Path
from scripts.qualify_expanded_cms_integration import SOURCES,TOTAL,verify_bytes,move_cost_table,verify_original,safe_table
class ExpandedCMSIntegrationTests(unittest.TestCase):
    def test_exact_pins_and_scope(self):
        self.assertEqual(sum(x[2] for x in SOURCES.values()),TOTAL)
        data=b"synthetic";pin={"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
        verify_bytes(data,pin)
        with self.assertRaises(ValueError):verify_bytes(b"synthetix",pin)
        with self.assertRaises(ValueError):safe_table("a; drop")
    def test_cost_namespaces(self):
        with sqlite3.connect(":memory:") as db:
            for target in ("hospital_cost_report","snf_cost_report"):
                db.execute("CREATE TABLE cost_report(ccn TEXT,state TEXT)")
                db.execute("CREATE INDEX cost_report_ccn ON cost_report(ccn,state)")
                db.execute("INSERT INTO cost_report VALUES('synthetic','NY')")
                move_cost_table(db,target)
                self.assertEqual(db.execute("SELECT count(*) FROM "+target).fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM hospital_cost_report").fetchone()[0],1)
    def test_original_content_guard(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"baseline.sqlite3"
            with sqlite3.connect(path) as old:
                old.execute("CREATE TABLE records(id INTEGER PRIMARY KEY,value TEXT)")
                old.execute("INSERT INTO records VALUES(1,'approved')")
            with sqlite3.connect(":memory:") as db,sqlite3.connect(path) as old:
                old.backup(db)
                self.assertEqual(verify_original(db,path,{"records"}),{"records":1})
                db.execute("UPDATE records SET value='changed'")
                db.commit()
                with self.assertRaises(ValueError):verify_original(db,path,{"records"})
