import sqlite3,tempfile,unittest,zipfile
from pathlib import Path
from scripts import archive_hcris_numeric_partitions as m,archive_hcris_form_indexes as idx

class NumericPartitionTests(unittest.TestCase):
    def fixture(self,root):
        p=root/"source.zip";i=root/"index.sqlite3"
        with zipfile.ZipFile(p,"w") as z:
            for y in ("2023","2024"):
                z.writestr(f"FORM_{y}_rpt.csv","1,private header\n")
                z.writestr(f"FORM_{y}_nmrc.csv","1,A000000,00100,00100,12.30\n1,A000000,00100,00100,-5.5\n2,A000000,00100,00100,99\n1,bad!,00100,00100,4\n")
                z.writestr(f"FORM_{y}_alpha.csv","1,A000000,00100,00100,secret alpha text\n")
        prior=idx.project(p,i)
        return p,i,prior
    def test_selected_year_preserves_exact_value_and_ordinal(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,i,prior=self.fixture(root);out=root/"numeric.sqlite3"
            s=m.project(p,i,out,prior,("2024",))
            self.assertEqual(s["stored_rows"],2);self.assertEqual(s["input_numeric_rows"],4)
            self.assertEqual(s["unresolved_parent_rows"],1);self.assertEqual(s["coordinate_review_rows"],1)
            self.assertEqual(s["repeated_coordinate_rows"],1);self.assertFalse(s["new_publisher_release"])
            with sqlite3.connect(out) as db:
                self.assertEqual(db.execute("SELECT source_year,ordinal,value_text,value_state FROM numeric_cells ORDER BY ordinal").fetchall(),[("2024",1,"12.30","positive"),("2024",2,"-5.5","negative")])
                self.assertEqual(db.execute("SELECT count(*) FROM report_references").fetchone()[0],1)
            self.assertNotIn(b"secret alpha text",out.read_bytes())
    def test_prior_count_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,i,prior=self.fixture(root)
            with sqlite3.connect(i) as db:db.execute("UPDATE reports SET numeric_rows=999 WHERE source_year='2024'")
            with self.assertRaises(ValueError):m.project(p,i,root/"numeric.sqlite3",prior,("2024",))
    def test_scope_validation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p,i,prior=self.fixture(root)
            with self.assertRaises(ValueError):m.project(p,i,root/"numeric.sqlite3",prior,("2026",))
