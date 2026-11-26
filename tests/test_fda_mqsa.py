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
            self.assertEqual(len(list(db.execute("PRAGMA table_info(mqsa_projection)"))),9)

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

    def test_pipe_rejection_reasons_without_rows(self):
        good="Clinic|Street|||City|PR|00901|phone|fax"
        bad="Clinic|Street||||PR|00901|phone|fax"
        wide="X"*76+"|Street|||City|PR|00901|phone|fax"
        with tempfile.TemporaryDirectory() as tmp,sqlite3.connect(":memory:") as db:
            a=audit_archive(db,self.source(tmp,"\n".join([good,bad,wide])))
            self.assertEqual(a["pipe_rejected_rows"],2)
            self.assertEqual(a["pipe_rejection_reason_counts"],{"missing_city":1,"width_name":1})
            self.assertEqual(a["layout_valid_row_counts"]["pipe"],1)
            self.assertEqual(a["stored_rows"],0)
            self.assertNotIn("Clinic",str(a))

    def test_explicit_width_exception_preserves_full_address_and_flags(self):
        good="Clinic|Street|||City|PR|00901|phone|fax"
        address="A"*51
        wide="Clinic|"+address+"|||City|PR|00901|phone|fax"
        with tempfile.TemporaryDirectory() as tmp,sqlite3.connect(":memory:") as db:
            p=self.source(tmp,good+"\n"+wide+"\n")
            self.assertEqual(audit_archive(db,p)["stored_rows"],0)
            a=audit_archive(db,p,allow_pinned_width_exception=True)
            self.assertEqual((a["stored_rows"],a["schema_exception_rows"]),(2,1))
            self.assertEqual(db.execute("SELECT address1,schema_exception FROM mqsa_projection WHERE ordinal=2").fetchone(),(address,"width_address1"))
            self.assertIsNone(db.execute("SELECT schema_exception FROM mqsa_projection WHERE ordinal=1").fetchone()[0])
            self.assertNotIn(address,str(a))

    def test_width_exception_does_not_accept_other_reasons(self):
        with tempfile.TemporaryDirectory() as tmp,sqlite3.connect(":memory:") as db:
            p=self.source(tmp,"Clinic|Street|||City|PR|00901|phone|fax\nClinic|Street||||PR|00901|phone|fax")
            with self.assertRaises(ValueError):
                audit_archive(db,p,allow_pinned_width_exception=True)

    def test_archive_boundary(self):
        with tempfile.TemporaryDirectory() as tmp,sqlite3.connect(":memory:") as db:
            with self.assertRaises(ValueError):
                audit_archive(db,self.source(tmp,"test", "../public.txt"))
