import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
import facilitysignal as fs
from collect_ownership import init
from integrate_ownership import copy_tables,TABLES
from ownership_evidence import profile

class OwnershipIntegrationTests(unittest.TestCase):
    def test_copy_and_candidate_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/"base.sqlite3";other=root/"owner.sqlite3"
            fs.init(target)
            with closing(sqlite3.connect(other)) as source:
                init(source)
                with source:
                    for key,n in (("hospital-enrollment",2),("hospital-owner",2)):
                        source.execute("INSERT INTO pecos_releases VALUES(?,?,?,?,?,?,?,?,?,?)",(key,"2026-11","2026-11-24","https://example.invalid/api","https://example.invalid/data","hash",n,n,0,"utf-8"))
                    for ordinal,state in ((2,"NY"),(3,"CA")):
                        source.execute("INSERT INTO pecos_enrollment_rows VALUES(?,?,?,?,?,?,?,?)",("hospital-enrollment",ordinal,"e"+str(ordinal),"p"+str(ordinal),"123456","npi","org",json.dumps({"STATE":state})))
                        source.execute("INSERT INTO pecos_org_role_rows VALUES(?,?,?,?,?,?,?,?,?)",("hospital-owner",ordinal,"e"+str(ordinal),"p"+str(ordinal),"owner","organization","role","text","{}"))
            before=other.read_bytes()
            with closing(fs.connect(target)) as db:
                with db:
                    rid=db.execute("INSERT INTO releases(dataset,published_on,imported_at,sha256,input_rows,stored_rows,duplicate_rows,source_url) VALUES(?,?,?,?,?,?,?,?)",("hospital","2026-11","2026-11","hash",1,1,0,"https://example.invalid")).lastrowid
                    db.execute("INSERT INTO facilities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("hospital","123456","Example","Street","City","NY","00000","","Hospital","","","","",rid))
                self.assertEqual(profile(db,"hospital","123456")["status"],"not_loaded")
                copy_tables(db,other)
                result=profile(db,"hospital","123456")
                self.assertEqual((result["status"],result["enrollment_rows"],result["organization_role_rows"],result["other_state_or_missing_rows"]),("same_state_identifier_candidate",1,1,1))
                self.assertEqual(profile(db,"hospital","' OR 1=1")["status"],"unsupported_or_invalid_identifier")
                self.assertEqual(profile(db,"hospital","000000")["status"],"facility_not_found")
                with self.assertRaises(ValueError): copy_tables(db,other)
                self.assertEqual(db.execute("SELECT count(*) FROM pecos_org_role_rows").fetchone()[0],2)
            self.assertEqual(other.read_bytes(),before)
