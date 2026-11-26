import sqlite3,tempfile,unittest
from pathlib import Path
from scripts import archive_pecos_ppef_corroboration as x
from scripts import azure_source_archive as storage
class Tests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE enrollment_observations(ordinal INTEGER PRIMARY KEY,enrollment_id TEXT UNIQUE,pac_id TEXT,npi TEXT,provider_type_code TEXT)")
        self.npi=next("123456789"+str(i) for i in range(10) if x.identity.npi_valid("123456789"+str(i)))
        self.other=next("123456788"+str(i) for i in range(10) if x.identity.npi_valid("123456788"+str(i)))
        self.db.executemany("INSERT INTO enrollment_observations VALUES(?,?,?,?,?)",[(2,"A"*15,"123",self.npi,"00-09"),(3,"B"*15,"124",self.other,"00-85"),(4,"C"*15,"123",self.npi,"00-09")])
    def tearDown(self):self.db.close()
    def test_exact_conflict_and_alternative(self):
        self.assertEqual(x.compare(self.db,"A"*15,"123",self.npi,"00-09"),(2,"exact_all_keys",1,1,1,None))
        self.assertEqual(x.compare(self.db,"B"*15,"123",self.npi,"00-09"),(3,"exact_enrollment_id_conflict",0,0,0,None))
        self.assertEqual(x.compare(self.db,"D"*15,"123",self.npi,"00-09"),(None,"no_exact_enrollment_id",None,None,None,2))
        self.assertEqual(x.compare(self.db,"","123",self.npi,"00-09"),(None,"key_shape_review",None,None,None,None))
    def test_projection_references_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"projection.sqlite3"
            rows=[("hospital-enrollment",i,e,"123",self.npi,"00-09","same_state_ccn","same","exact_enrollment_pac") for i,e in ((2,"A"*15),(3,"B"*15),(4,"D"*15),(5,""))]
            r=x.projection(p,self.db,rows)
            self.assertEqual(r["stored_enrollment_evidence_rows"],4)
            self.assertEqual(r["dispositions"],{"exact_all_keys":1,"exact_enrollment_id_conflict":1,"no_exact_enrollment_id":1,"key_shape_review":1})
            with sqlite3.connect(p) as db:
                data=str(list(db.iterdump()))
                self.assertNotIn(self.npi,data)
                self.assertNotIn("A"*15,data)
                self.assertEqual(db.execute("SELECT ppef_candidate_ordinal FROM enrollment_corroboration WHERE source_ordinal=4").fetchone(),(None,))
    def test_scope(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                x.projection(Path(d)/"out.sqlite3",self.db,[("snf-enrollment",2,"A"*15,"123",self.npi,"00-09","same_state_ccn","same","exact_enrollment_pac")])
        self.assertTrue(storage.prefix_for(x.KEY,"a"*64).startswith(storage.PREFIX+"/"))
