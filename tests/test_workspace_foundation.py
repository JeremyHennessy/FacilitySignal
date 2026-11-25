import tempfile
import unittest
from pathlib import Path
from contextlib import closing
import facilitysignal as fs
from collect_ownership import init as ownership_init

class WorkspaceFoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"fixture.sqlite3"
        fs.init(self.path)
        self.db=fs.connect(self.path)
        self.addCleanup(self.db.close)

    def test_missing_families_are_null_not_zero(self):
        result=fs.overview(self.db)
        for key in ("facility_records","finding_records","certification_records","hospital_survey_records","enrollment_records","organization_role_records","ownership_change_records"):
            self.assertIsNone(result[key],key)
        self.assertEqual(result["loaded_releases"],[])
        page=fs.render_overview(self.db)
        self.assertIn("not additive",page)
        self.assertIn("/ownership-coverage?kind=enrollment",page)
        self.assertIn("Skip to content",page)

    def seed(self):
        db=self.db
        db.execute("INSERT INTO releases VALUES(1,'hospital','2025-01-01','2025-01-02','fixture',2,2,0,'https://example.test')")
        db.execute("INSERT INTO current_release VALUES('hospital',1)")
        for ccn,name,city,address,zip_code in [("010001","Alpha fixture","Testville","12 Main St","01234"),("010002","Zulu fixture","Elsewhere","16 Second St","01235")]:
            db.execute("INSERT INTO facilities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("hospital",ccn,name,address,city,"AL",zip_code,"County","Hospital","","","","",1))
        db.execute("INSERT INTO certification_releases VALUES('clia','CLIA fixture','2025-01','https://example.test','https://example.test','fixture',2,'2025-01-02','{}')")
        db.execute("INSERT INTO certification_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("clia",1,"fixture","010001","<Registry fixture>","12 Main St","Testville","AL","01234","C","","2020-01-01","2024-01-01","X"))
        db.execute("INSERT INTO qcor_hospital_releases VALUES(1,'fixture','2025-01-02','https://example.test',1,1,1)")
        db.execute("INSERT INTO qcor_hospital_current VALUES(1,1)")
        db.execute("INSERT INTO qcor_hospital_rows VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(1,1,"fixture","010001","Alpha fixture","","12 Main St","Testville","AL","01234","","event","2025-01-01","","","Memo","","memo"))
        ownership_init(db)
        db.execute("INSERT INTO pecos_releases VALUES('hospital-enrollment','2025-01','2025-01-01','https://example.test','https://example.test','fixture',1,1,0,'utf-8')")
        db.execute("INSERT INTO pecos_enrollment_rows VALUES(?,?,?,?,?,?,?,?)",("hospital-enrollment",1,"PRIVATE-FIXTURE","PAC","010001","NPI","PRIVATE-ORG","{}"))
        db.commit()

    def test_live_counts_manifest_mismatch_and_no_ownership_projection(self):
        self.seed()
        result=fs.overview(self.db)
        self.assertEqual(result["facility_records"],2)
        self.assertEqual(result["certification_records"],1)
        self.assertEqual(result["hospital_survey_records"],1)
        self.assertEqual(result["enrollment_records"],1)
        self.assertIsNone(result["organization_role_records"])
        self.assertIn("Manifest declares 2",fs.render_overview(self.db))
        page=fs.render_ownership_coverage(self.db,{"kind":"enrollment"})
        self.assertNotIn("PRIVATE-ORG",page)
        self.assertNotIn("PRIVATE-FIXTURE",page)

    def test_search_identifier_address_zip_sort_and_provenance(self):
        self.seed()
        result=fs.global_search(self.db,{"q":"010001","mode":"identifier"})
        self.assertEqual([g["result"]["total"] for g in result["groups"]],[1,1])
        self.assertEqual(fs.global_search(self.db,{"q":"12 Main St"})["groups"][0]["result"]["total"],1)
        self.assertEqual(fs.global_search(self.db,{"q":"01234"})["groups"][1]["result"]["total"],1)
        self.assertEqual(fs.global_search(self.db,{"q":"01000","mode":"identifier"})["groups"][0]["result"]["total"],0)
        self.assertEqual(fs.paged(self.db,"facilities",{"sort":"name_desc","limit":"1"})["rows"][0]["ccn"],"010002")
        self.assertEqual(fs.paged(self.db,"facilities",{"q":"%","sort":"DROP TABLE facilities"})["total"],0)
        page=fs.render_search(self.db,{"q":"010001","mode":"identifier"})
        self.assertIn("/certification?registry=clia&amp;row=1",page)
        self.assertIn("&lt;Registry fixture&gt;",page)
        detail=fs.render_certification_detail(self.db,{"registry":"clia","row":"1"})
        self.assertIn("2024-01-01",detail)
        self.assertIn("Source status code",detail)
        self.assertIsNone(fs.render_certification_detail(self.db,{"registry":"clia","row":"99"}))
        with self.assertRaises(ValueError):
            fs.render_certification_detail(self.db,{"registry":"clia","row":"-1"})
