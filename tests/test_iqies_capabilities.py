import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
import facilitysignal as fs
from iqies_capabilities import DDL,normalize_value,scope_mapping,profile,DICT_SHA

class CapabilityTests(unittest.TestCase):
    def test_missing_distinct_from_negative_and_zero(self):
        for text,kind,expected in (
            ("0","count",("reported_count",0)),("001","count",("reported_count",1)),
            ("Not Available","count",("not_available",None)),("Not Applicable","count",("not_applicable_conflict",None)),
            ("","count",("blank",None)),("No","boolean",("reported_no",None)),
            ("Yes","boolean",("reported_yes",None)),("N","boolean",("unrecognized",None)),
            ("-1","count",("unrecognized",None)),("3.5","count",("unrecognized",None))):
            self.assertEqual(normalize_value(text,kind),expected)
    def test_scope_requires_documented_mapping(self):
        _,scopes=scope_mapping([(8,"Ambulatory Surgical Center"),(9,"End-Stage Renal Disease"),(3,"Home Health Agency")])
        self.assertEqual(scopes,{"8":"ASC","9":"ESRD"})
        with self.assertRaises(ValueError):scope_mapping([(8,"Other"),(9,"End-Stage Renal Disease")])
        with self.assertRaises(ValueError):scope_mapping([(8,"Ambulatory Surgical Center"),(8,"End-Stage Renal Disease")])
    def test_profile_source_scope_and_no_missing_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            dbpath=Path(tmp)/"x.sqlite3";fs.init(dbpath)
            with closing(sqlite3.connect(dbpath)) as db:
                db.execute("PRAGMA foreign_keys=ON")
                self.assertEqual(profile(db,"000123")["status"],"not_loaded")
                db.executescript(DDL)
                with db:
                    db.execute("INSERT INTO certification_releases VALUES(?,?,?,?,?,?,?,?,?)",("iqies","test","2026-Q3","api","url","digest",1,"date","{}"))
                    db.execute("INSERT INTO certification_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("iqies",1,"hash","000123","Example","Street","City","NY","00000","8","","","",""))
                    db.execute("INSERT INTO iqies_capability_release VALUES(1,?,?,?,?,?,?)",("digest",DICT_SHA,"2026-Q3","dictionary",1,"date"))
                    db.execute("INSERT INTO iqies_capability_observations VALUES(?,?,?,?,?,?)",("iqies",1,"oprtg_room_cnt","ASC","reported_count",0))
                    db.execute("INSERT INTO iqies_capability_observations VALUES(?,?,?,?,?,?)",("iqies",1,"procedure_room_cnt","ASC","not_available",None))
                result=profile(db,"000123")
                self.assertEqual(result["status"],"source_observations")
                vals={r["field"]:r["count_value"] for r in result["rows"]}
                self.assertEqual(vals,{"oprtg_room_cnt":0,"procedure_room_cnt":None})
                self.assertEqual(profile(db,"000124")["status"],"no_qualified_observations")
                self.assertEqual(profile(db,"' OR 1=1")["status"],"invalid_identifier")
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute("INSERT INTO iqies_capability_observations VALUES(?,?,?,?,?,?)",("iqies",99,"oprtg_room_cnt","ASC","reported_count",1))
