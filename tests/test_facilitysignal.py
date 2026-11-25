import csv
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import facilitysignal as fs

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.db=self.root/"test.sqlite3"
        fs.init(self.db)
        self.fields=["Facility ID","Facility Name","Address","City/Town","State","ZIP Code","Hospital Type","Hospital Ownership"]
        self.hospital=["010001","Fixture only","1 Test Street","Testville","AL","01234","Acute Care Hospitals","Test"]
    def tearDown(self):
        self.tmp.cleanup()
    def write_csv(self,fields,records):
        p=self.root/"fixture.csv"
        with p.open("w",newline="",encoding="utf-8") as f:
            w=csv.writer(f)
            w.writerow(fields)
            w.writerows(records)
        return p
    def test_empty(self):
        with closing(fs.connect(self.db)) as db:
            self.assertIsNone(fs.overview(db)["facility_records"])
            self.assertEqual(fs.overview(db)["source_entries"],176)
    def test_snapshot_and_search(self):
        p=self.write_csv(self.fields,[self.hospital])
        out=fs.import_csv(self.db,"hospital",p,"2025-01-01",1)
        self.assertEqual(out["stored_rows"],1)
        self.assertEqual(fs.import_csv(self.db,"hospital",p,"2025-01-01",1)["status"],"unchanged")
        with closing(fs.connect(self.db)) as db:
            r=fs.paged(db,"facilities",{"q":"010001","state":"AL"})
            self.assertEqual(r["total"],1)
            self.assertEqual(r["rows"][0]["zip"],"01234")
            self.assertIn("Fixture only",fs.render_detail(db,{"dataset":"hospital","ccn":"010001"}))
            self.assertEqual(fs.paged(db,"facilities",{"q":"%"} )["total"],0)
    def test_bad_refresh_preserves_snapshot(self):
        p=self.write_csv(self.fields,[self.hospital])
        fs.import_csv(self.db,"hospital",p,"2025-01-01",1)
        with self.assertRaises(ValueError):
            fs.import_csv(self.db,"hospital",p,"2025-01-02",2)
        p=self.write_csv(self.fields,[self.hospital,self.hospital])
        with self.assertRaises(Exception):
            fs.import_csv(self.db,"hospital",p,"2025-01-02",2)
        with closing(fs.connect(self.db)) as db:
            self.assertEqual(fs.overview(db)["facility_records"],1)
            self.assertEqual(len(fs.rows(db,"SELECT * FROM releases")),1)
    def test_nursing_findings(self):
        p=self.write_csv(["CMS Certification Number (CCN)","Provider Name","Provider Address","City/Town","State","ZIP Code","Number of Certified Beds"],[["015009","Fixture nursing","2 Test St","Testville","AL","01234","100"]])
        fs.import_csv(self.db,"nursing",p,"2025-01-01",1)
        fields=["CMS Certification Number (CCN)","Provider Name","State","Survey Date","Deficiency Prefix","Deficiency Tag Number","Deficiency Description","Scope Severity Code","Deficiency Corrected","Correction Date"]
        row=["015009","Fixture nursing","AL","2024-12-01","F","0880","Synthetic fixture","D","Corrected","2024-12-05"]
        p=self.write_csv(fields,[row,row])
        result=fs.import_csv(self.db,"nursing-health",p,"2025-01-01",2)
        self.assertEqual(result["duplicate_rows"],1)
        with closing(fs.connect(self.db)) as db:
            self.assertEqual(fs.paged(db,"findings",{"ccn":"015009"})["total"],1)
            self.assertIn("Synthetic fixture",fs.render_detail(db,{"dataset":"nursing","ccn":"015009"}))
            self.assertEqual(fs.overview(db)["finding_records"],1)
    def test_dialysis_and_escaping(self):
        p=self.write_csv(["CMS Certification Number (CCN)","Facility Name","Address Line 1","Address Line 2","City/Town","State","ZIP Code","# of Dialysis Stations"],[["012345","<script>fixture</script>","3 Test","Suite 2","Testville","PR","00901","12"]])
        fs.import_csv(self.db,"dialysis",p,"2025-01-01",1)
        with closing(fs.connect(self.db)) as db:
            page=fs.render_list(db,"facilities",{})
            self.assertIn("&lt;script&gt;",page)
            self.assertNotIn("<script>",page)
            self.assertEqual(fs.paged(db,"facilities",{})["rows"][0]["capacity"],"12")
    def test_fire_and_expanded_categories(self):
        p=self.write_csv(["CMS Certification Number (CCN)","Facility Name","Address Line 1","City","State","ZIP Code"],[["010001","Fixture hospice","3 Test St","Testville","AL","01234"]])
        fs.import_csv(self.db,"hospice",p,"2025-01-01",1)
        fields=["CMS Certification Number (CCN)","Provider Name","State","Survey Date","Deficiency Prefix","Deficiency Tag Number","Deficiency Description","Scope Severity Code","Deficiency Corrected","Correction Date"]
        p=self.write_csv(fields,[["015009","Fixture nursing","AL","12/01/2024","K","0321","Fixture fire citation","D","Corrected","12/05/2024"]])
        fs.import_csv(self.db,"nursing-fire",p,"2025-01-01",1)
        with closing(fs.connect(self.db)) as db:
            self.assertEqual(fs.overview(db)["facility_records"],1)
            self.assertEqual(fs.overview(db)["finding_records"],1)
            self.assertEqual(fs.paged(db,"findings",{"dataset":"nursing-fire"})["rows"][0]["survey_date"],"2024-12-01")

    def test_sources_and_invalid_pages(self):
        self.assertEqual(fs.sources({})["total"],176)
        self.assertEqual(len(fs.sources({"limit":"3"})["rows"]),3)
        with self.assertRaises(ValueError):
            fs.page_args({"page":"abc"})

if __name__=="__main__":
    unittest.main()
