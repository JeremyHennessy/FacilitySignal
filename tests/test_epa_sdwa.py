import csv
import io
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from scripts.qualify_epa_sdwa import ingest,MEMBER,allowed,URL

class EpaSdwaTests(unittest.TestCase):
    def archive(self,root,rows,header=None,member=MEMBER):
        p=Path(root)/"test.zip"
        buf=io.StringIO()
        writer=csv.writer(buf)
        writer.writerow(header or ["PWSID","STATE_CODE","PWS_TYPE_CODE","PWS_ACTIVITY_CODE","SERVICE_AREA_TYPE_CODE","PWS_NAME"])
        writer.writerows(rows)
        with zipfile.ZipFile(p,"w",zipfile.ZIP_DEFLATED) as z:z.writestr(member,buf.getvalue())
        return p

    def test_projection_excludes_names_and_reconciles(self):
        with tempfile.TemporaryDirectory() as t,sqlite3.connect(":memory:") as db:
            path=self.archive(t,[["NY1234567","NY","CWS","A","OT","Name not retained"],
                                 ["NY1234567","NY","CWS","A","OT","Duplicate"],
                                 ["bad","CA","CWS","I","OT","Malformed"],
                                 ["CA1234567","CA","NTNCWS","I","","Other name"]])
            audit=ingest(db,path)
            self.assertEqual((audit["input_rows"],audit["stored_unique_pws_keys"],audit["duplicate_keys"],audit["invalid_keys"]),(4,2,1,1))
            self.assertEqual(audit["qualification"],"key_anomalies_require_review")
            self.assertNotIn("Name not retained",str(audit))
            self.assertEqual([c[1] for c in db.execute("PRAGMA table_info(pws_key)")],["pwsid","state","kind","activity"])

    def test_schema_and_membership_fail_closed(self):
        with tempfile.TemporaryDirectory() as t,sqlite3.connect(":memory:") as db:
            p=self.archive(t,[],member="../"+MEMBER)
            with self.assertRaises(ValueError):ingest(db,p)
        with tempfile.TemporaryDirectory() as t,sqlite3.connect(":memory:") as db:
            p=self.archive(t,[],header=["PWSID","PWSID"])
            with self.assertRaises(ValueError):ingest(db,p)

    def test_redirect_boundary(self):
        self.assertTrue(allowed(URL))
        self.assertFalse(allowed(URL+"?x=1"))
        self.assertFalse(allowed(URL.replace("echo.epa.gov","example.com")))
