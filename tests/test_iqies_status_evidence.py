import sqlite3,unittest
from iqies_status_evidence import DDL,termination,survey,parsed_date,parse_domain,profile

class StatusEvidenceTests(unittest.TestCase):
    def test_code_not_operation(self):
        domain={"00":"Active","01":"Voluntary Merger/Closure"}
        for raw,expected in (("00",("00","recognized")),("1",("01","recognized")),("","blank"),("99","unknown")):
            if isinstance(expected,str):expected=(None,expected)
            self.assertEqual(termination(raw,domain),expected)
    def test_missing_separate(self):
        self.assertEqual(survey("No"),"reported_no")
        self.assertEqual(survey(""),"blank")
        self.assertEqual(survey("N"),"unknown")
        self.assertEqual(parsed_date("2026-09-30"),("2026-09-30","reported"))
        self.assertEqual(parsed_date("2026-02-30"),(None,"unknown"))
        self.assertEqual(parsed_date(""),(None,"blank"))
    def test_domain_rejects_duplicates_and_incomplete(self):
        with self.assertRaises(ValueError):parse_domain([("00","Active"),("0","Other")])
        with self.assertRaises(ValueError):parse_domain([("00","Active")])
    def test_fk_and_profile(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript("CREATE TABLE certification_records(registry TEXT,row_number INTEGER,provider_id TEXT,PRIMARY KEY(registry,row_number));")
            self.assertEqual(profile(db,"000123")["status"],"not_loaded")
            db.executescript(DDL)
            db.execute("INSERT INTO certification_records VALUES('iqies',1,'000123')")
            db.execute("INSERT INTO iqies_status_release VALUES(1,'source','dictionary','period','url',1,'date')")
            db.execute("INSERT INTO iqies_termination_dictionary VALUES('00','Active')")
            db.execute("INSERT INTO iqies_status_observations VALUES('iqies',1,'00','recognized','2','Source name','No','reported_no',NULL,'blank')")
            result=profile(db,"000123")
            self.assertEqual(result["rows"][0]["termination_code_label"],"Active")
            self.assertEqual(result["rows"][0]["federal_status_name"],"Source name")
            self.assertNotIn("active",result["rows"][0])
            self.assertEqual(profile(db,"000124")["status"],"no_qualified_observations")
            self.assertEqual(profile(db,"' OR 1=1")["status"],"invalid_identifier")
            with self.assertRaises(sqlite3.IntegrityError):db.execute("INSERT INTO iqies_status_observations VALUES('iqies',2,'00','recognized',NULL,NULL,NULL,'blank',NULL,'blank')")
