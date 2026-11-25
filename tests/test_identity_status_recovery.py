import sqlite3
import unittest
from pathlib import Path
from identity_status_recovery import date_shape,match_state,agreement,zip5,build_candidates,profile

class IdentityStatusTests(unittest.TestCase):
    def test_dates_never_guess(self):
        for raw,expected in (("","blank"),("Not Available","not_available"),("Not Applicable","not_applicable"),
            ("2024-02-29","valid_iso_date"),("2025-02-29","invalid_iso_date"),
            ("2025-01-01T00:00:00Z","valid_iso_datetime"),("01/02/2025","slash_date_uninterpreted"),
            ("20250101","eight_digit_uninterpreted"),("12345","numeric_uninterpreted")):
            self.assertEqual(date_shape(raw),expected)
    def test_scope_and_missing(self):
        self.assertEqual(match_state("NY","NY","01","1"),"same_state")
        self.assertEqual(match_state("NY","CA","01","1"),"state_conflict")
        self.assertEqual(match_state("NY","","01","1"),"state_missing")
        self.assertEqual(match_state("NY","NY","3","1"),"provider_type_conflict")
        self.assertIsNone(agreement("",""))
        self.assertEqual(agreement("A  ROAD","a road"),1)
        self.assertEqual(zip5("00123-4567"),"00123")
        self.assertEqual(zip5("123"),"")
    def test_candidate_pairs_never_merge_or_cross_clia(self):
        with sqlite3.connect(":memory:") as db:
            db.executescript((Path(__file__).resolve().parents[1]/"schema.sql").read_text())
            db.execute("INSERT INTO releases VALUES(1,'hospital','2026-11-01','date','hash',1,1,0,'url')")
            db.execute("INSERT INTO facilities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("hospital","001234","F","1 Main","Town","NY","00123","","Hospital","","","","",1))
            for reg in ("qies","clia","iqies"):
                db.execute("INSERT INTO certification_releases VALUES(?,?,?,?,?,?,?,?,?)",(reg,reg,"period","api","url","hash",1,"date","{}"))
            for reg,n,state,ptype in (("qies",1,"NY","01"),("qies",2,"CA","01"),("qies",3,"NY","03"),("clia",1,"NY","01"),("iqies",1,"NY","01")):
                db.execute("INSERT INTO certification_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(reg,n,"hash","001234","F","1 MAIN","TOWN",state,"00123-0000",ptype,"","","",""))
            db.commit()
            self.assertEqual(profile(db,"hospital","001234")["status"],"not_loaded")
            result=build_candidates(db)["hospital"]
            self.assertEqual(result["facility_rows"],1)
            self.assertEqual(result["exact_identifier_candidate_pairs"],3)
            self.assertEqual(result["pair_states"],{"same_state":1,"state_conflict":1,"provider_type_conflict":1})
            self.assertEqual(result["same_state_type_and_exact_address_city_zip_text_pairs"],1)
            self.assertEqual(len(profile(db,"hospital","001234")["candidates"]),3)
            self.assertEqual(db.execute("SELECT count(*) FROM facilities").fetchone()[0],1)
            self.assertEqual(profile(db,"hospital","' OR 1=1")["status"],"invalid_or_unsupported_identifier")
            with self.assertRaises(ValueError):build_candidates(db)
