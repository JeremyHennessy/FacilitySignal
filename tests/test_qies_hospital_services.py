import sqlite3
import unittest
from qies_hospital_services import DDL,FIELDS,REFERENCE,classify,is_hospital

class QiesHospitalServicesTests(unittest.TestCase):
    def test_scope_is_hospital_category_only(self):
        for value in ("01","1"," 01 "):self.assertTrue(is_hospital(value))
        for value in ("03","02","10","", "1.0","001"):self.assertFalse(is_hospital(value))
    def test_historical_domain_not_missing(self):
        for value in REFERENCE:self.assertEqual(classify(value),("historical_domain_code",value))
        for value,state in (("","blank"),("Not Available","not_available"),("Not Applicable","not_applicable"),("4","unrecognized"),("0.0","unrecognized")):
            self.assertEqual(classify(value),(state,None))
        self.assertEqual(len(FIELDS),12)
    def test_foreign_keys_and_code_constraint(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript("CREATE TABLE certification_records(registry TEXT,row_number INTEGER,PRIMARY KEY(registry,row_number));"+DDL)
            db.execute("INSERT INTO certification_records VALUES('qies',1)")
            db.execute("INSERT INTO qies_hospital_service_observations VALUES('qies',1,'CT_SCAN_SRVC_CD','blank',NULL)")
            with self.assertRaises(sqlite3.IntegrityError):db.execute("INSERT INTO qies_hospital_service_observations VALUES('qies',1,'PET_SCAN_SRVC_CD','blank','0')")
            with self.assertRaises(sqlite3.IntegrityError):db.execute("INSERT INTO qies_hospital_service_observations VALUES('qies',2,'PET_SCAN_SRVC_CD','historical_domain_code','1')")
