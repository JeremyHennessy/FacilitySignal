import csv,sqlite3,tempfile,unittest
from pathlib import Path
from scripts import archive_ppef_enrollment as m

class PPEFTests(unittest.TestCase):
    def test_series_resource_selection(self):
        url="https://data.cms.gov/data-api/v1/dataset/test/resources"
        cat={"datasetSeries":[{"title":m.TITLE,"last":{"@id":"version"}}],"dataset":[{"@id":"version","accessLevel":"public","distribution":[{"resourcesAPI":url}]}]}
        self.assertEqual(m.catalog_selection(cat)["resource_api"],url)
        r={"data":[{"name":"Enrollment Sub-File","downloadURL":"https://data.cms.gov/files/enrollment.zip"},{"name":"Reassignment Sub-File","downloadURL":"https://data.cms.gov/files/reassign.zip"}]}
        self.assertTrue(m.resource_selection(r)["zipped"])
        with self.assertRaises(Exception):m.resource_selection({"data":r["data"]*2})
    def test_projection_no_individual_records(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);reg=root/"registry.db";src=root/"source.csv";out=root/"out.db"
            with sqlite3.connect(reg) as db:
                db.execute("CREATE TABLE organization_fields(npi TEXT PRIMARY KEY)")
                db.execute("INSERT INTO organization_fields VALUES('1234567893')")
            cols=list(m.FIELDS)+["NAME"]
            with src.open("w",newline="") as f:
                w=csv.writer(f);w.writerow(cols)
                w.writerow(["1234567893","1234567890","A12345678901234","00-09","do not retain"])
                w.writerow(["1234567893","1234567890","B12345678901234","bad","do not retain"])
                w.writerow(["invalid","1234567890","C12345678901234","14-01","private"])
            s=m.project(src,False,reg,out)
            self.assertEqual(s["input_rows"],3);self.assertEqual(s["stored_rows"],1);self.assertEqual(s["institutional_key_or_code_review"],1)
            self.assertNotIn(b"do not retain",out.read_bytes())
