"""Gate the additional iQIES projection against the pinned aggregate evidence."""
import sqlite3
import unittest
from contextlib import closing
from collections import Counter
from iqies_additional_services import DDL, RULES, classify, evidence

class AdditionalServiceTests(unittest.TestCase):
    def test_actual_aggregate_contract(self):
        definitions, counts = evidence()
        self.assertEqual(set(definitions), set(counts))
        self.assertEqual(Counter(scope for scope,row in RULES.values()), {"ASC":8,"ESRD":3})
        self.assertEqual(sum(sum(c.values()) for c in counts.values()), 93913)
        self.assertEqual(counts["orthpdc_srgry_sw"], {"reported_yes":2893,"reported_no":5147,"not_available":452})
        self.assertEqual(counts["incntr_nctrnl_srvc_sw"], {"reported_yes":12,"reported_no":8435,"not_available":212})
        self.assertIn("begun", definitions["incntr_nctrnl_srvc_sw"]["definition"])
        self.assertIn("continued", definitions["sp_home_trng_sprt_hd_sw"]["definition"])
    def test_fail_closed_values_and_scope(self):
        for field,(scope,_) in RULES.items():
            self.assertEqual(classify(field,scope,"Yes"),"reported_yes")
            self.assertEqual(classify(field,scope,"No"),"reported_no")
            self.assertEqual(classify(field,scope,"Not Available"),"not_available")
            self.assertIsNone(classify(field,"HHA","Not Applicable"))
            for raw in ("","Unknown","N","Not Applicable"):
                with self.assertRaises(ValueError):
                    classify(field,scope,raw)
            with self.assertRaises(ValueError):
                classify(field,"HHA","Yes")
    def test_transactional_extension_and_fk(self):
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("CREATE TABLE certification_records(registry TEXT,row_number INTEGER,PRIMARY KEY(registry,row_number))")
            db.execute("INSERT INTO certification_records VALUES('iqies',1)")
            db.commit()
            db.executescript("BEGIN IMMEDIATE;\n"+DDL)
            db.execute("INSERT INTO iqies_additional_service_observations VALUES('iqies',1,'ft_srgry_sw','ASC','reported_yes')")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO iqies_additional_service_observations VALUES('iqies',2,'ft_srgry_sw','ASC','reported_yes')")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO iqies_additional_service_observations VALUES('iqies',1,'ft_srgry_sw','ASC','reported_yes')")
            db.rollback()
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='iqies_additional_service_observations'").fetchone())
            self.assertEqual(db.execute("SELECT * FROM certification_records").fetchall(),[("iqies",1)])
