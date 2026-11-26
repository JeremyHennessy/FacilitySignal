import io
import csv
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from scripts.qualify_fda_mqsa import audit_archive, WIDTHS

class MQSATests(unittest.TestCase):
    def source(self, root, text, member="public.txt"):
        path=Path(root)/"source.zip"
        with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr(member,text)
        return path

    def test_fixed_projection_and_duplicate_reconciliation(self):
        row=("Synthetic Center","12 Test Road","","","Example","NY","12345","not retained","fax")
        line="".join(v.ljust(w) for v,w in zip(row,WIDTHS))
        with tempfile.TemporaryDirectory() as tmp,sqlite3.connect(":memory:") as db:
            a=audit_archive(db,self.source(tmp,line+"\n"+line+"\n"))
            self.assertEqual((a["stored_rows"],a["exact_parsed_row_duplicates"],a["repeated_projected_name_address_rows"]),(2,1,1))
            self.assertEqual(a["layout"],"fixed")
            self.assertEqual(a["jurisdiction_counts"],{"NY":2})
            self.assertNotIn("Synthetic Center",str(a))
            self.assertNotIn("not retained",str(list(db.execute("SELECT * FROM mqsa_projection"))))
            self.assertEqual(len(list(db.execute("PRAGMA table_info(mqsa_projection)"))),8)

    def test_delimited_projection(self):
        buf=io.StringIO()
        csv.writer(buf,delimiter="|").writerow(["Clinic","Street","","","City","PR","00901","phone","fax"])
        with tempfile.TemporaryDirectory() as tmp,sqlite3.connect(":memory:") as db:
            a=audit_archive(db,self.source(tmp,buf.getvalue()))
            self.assertEqual((a["layout"],a["stored_rows"],a["represented_us_jurisdictions"]),("pipe",1,1))

    def test_unknown_schema_preserves_no_rows(self):
        with tempfile.TemporaryDirectory() as tmp,sqlite3.connect(":memory:") as db:
            a=audit_archive(db,self.source(tmp,"unexpected record\n"))
            self.assertEqual((a["qualification"],a["unresolved_rows"],a["stored_rows"]),("schema_review_required",1,0))
            self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master").fetchone()[0],0)

    def test_archive_boundary(self):
        with tempfile.TemporaryDirectory() as tmp,sqlite3.connect(":memory:") as db:
            with self.assertRaises(ValueError):
                audit_archive(db,self.source(tmp,"test", "../public.txt"))
