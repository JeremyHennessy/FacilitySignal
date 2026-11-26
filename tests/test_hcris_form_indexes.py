import csv,io,sqlite3,tempfile,unittest,zipfile
from pathlib import Path
from scripts import archive_hcris_form_indexes as m

class FormIndexTests(unittest.TestCase):
    def test_report_index_and_no_values(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);z=p/"source.zip";db=p/"output.db"
            with zipfile.ZipFile(z,"w") as f:
                f.writestr("FORM_RPT.csv","1,private header\n2,private header\n")
                f.writestr("FORM_NMRC.csv","1,A000000,00100,00100,12.3\n2,A000000,00100,00100,9\n")
                f.writestr("FORM_ALPHNMRC.csv","1,A000000,00100,00100,private text\n")
            s=m.project(z,db)
            self.assertEqual(s["stored_rows"],2);self.assertEqual(s["screened_child_rows"],3)
            self.assertEqual(s["numeric_cell_values_retained"],0)
            with sqlite3.connect(db) as con:self.assertEqual(con.execute("SELECT * FROM reports ORDER BY report_key").fetchall(),[("1",1,1,1),("2",2,1,0)])
            self.assertNotIn(b"private text",db.read_bytes())
    def test_orphan_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);z=p/"bad.zip"
            with zipfile.ZipFile(z,"w") as f:
                f.writestr("FORM_RPT.csv","1,x\n");f.writestr("FORM_NMRC.csv","2,A000000,1,1,10\n");f.writestr("FORM_ALPHNMRC.csv","1,A000000,1,1,x\n")
            with self.assertRaises(Exception):m.project(z,p/"bad.db")
    def test_exact_publisher_link(self):
        page=m.BASE+"test";url="https://downloads.cms.gov/files/example.zip"
        self.assertEqual(m.resolve('<a href="'+url+'">Hospice 14 Data files</a>',page,"Hospice 14 Data files"),url)
        with self.assertRaises(Exception):m.resolve('<a href="https://example.com/example.zip">Hospice 14 Data files</a>',page,"Hospice 14 Data files")
