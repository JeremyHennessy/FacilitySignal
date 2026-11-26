import csv
import io
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from scripts.qualify_epa_sdwa import ingest,MEMBER,allowed,URL,key_format,shape_mask

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
            self.assertEqual(audit["accepted_key_format_counts"],{"standard":3})
            self.assertEqual(audit["invalid_key_format_counts"],{"wrong_length":1})
            self.assertNotIn("Name not retained",str(audit))
            self.assertEqual([c[1] for c in db.execute("PRAGMA table_info(pws_key)")],["pwsid","state","kind","activity"])

    def test_publisher_documented_identifier_formats(self):
        self.assertEqual(key_format("UTAH12345"),"utah")
        self.assertEqual(key_format("010123456"),"epa_region")
        self.assertEqual(key_format("100123456"),"epa_region")
        for key in ("000123456","110123456","UTAH1234X","utah12345","UTAH1234",""):
            self.assertNotIn(key_format(key),{"standard","utah","epa_region"})
        with tempfile.TemporaryDirectory() as t,sqlite3.connect(":memory:") as db:
            p=self.archive(t,[[k,"","CWS","A","",""] for k in
                ("NY1234567","UTAH12345","010123456","100123456")])
            a=ingest(db,p)
            self.assertEqual(a["qualification"],"clean_keys")
            self.assertEqual(a["accepted_key_format_counts"],{"standard":1,"utah":1,"epa_region":2})
            self.assertEqual(a["invalid_key_format_counts"],{})
            self.assertEqual(a["stored_unique_pws_keys"],4)
            self.assertEqual(db.execute("SELECT count(*) FROM pws_key WHERE pwsid='010123456'").fetchone()[0],1)

    def test_unresolved_key_shape_and_full_uniqueness(self):
        self.assertEqual(shape_mask("AB12C3456"),"AA99A9999")
        self.assertEqual(shape_mask("abc12-456"),"aaa99?999")
        self.assertEqual(shape_mask("secret"),"(other_length)")
        with tempfile.TemporaryDirectory() as t,sqlite3.connect(":memory:") as db:
            p=self.archive(t,[[k,"","CWS","A","",""] for k in
                ("NY1234567","AB12C3456","AB12C3456",""," UTAH12345 ")])
            a=ingest(db,p)
            self.assertEqual(a["qualification"],"key_anomalies_require_review")
            self.assertEqual(a["rejected_character_class_masks"],{"AA99A9999":2,"(other_length)":1})
            self.assertEqual((a["all_nonblank_unique_keys"],a["all_nonblank_duplicate_keys"],a["all_blank_keys"],a["whitespace_trimmed_key_rows"]),(3,1,1,1))
            self.assertNotIn("AB12C3456",str(a))
            self.assertEqual(db.execute("SELECT count(*) FROM sqlite_temp_master WHERE name='all_source_keys'").fetchone()[0],0)

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
