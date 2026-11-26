import sqlite3,tempfile,unittest,zipfile
from pathlib import Path
from scripts import archive_hcris_large_numeric as m,archive_hcris_form_indexes as idx
class LargeNumericTests(unittest.TestCase):
    def test_full_source_disjoint_partitions(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/"source.zip";i=root/"index.sqlite3"
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("FORM_RPT.csv","1,private header\n2,private header\n")
                z.writestr("FORM_NMRC.csv","1,A000000,00100,00100,12.30\n1,A000000,00100,00100,-5.5\n2,bad!,00100,00100,99\n2,A000000,00100,00100,4\n")
                z.writestr("FORM_ALPHA.csv","1,A000000,00100,00100,secret alpha text\n")
            prior=idx.project(p,i)
            plan=[("part1",1,2),("part2",3,4)]
            results=m.project(p,i,prior,plan,root)
            self.assertEqual(sum(r["summary"]["stored_rows"] for r in results),3)
            self.assertEqual(sum(r["summary"]["coordinate_review_rows"] for r in results),1)
            with sqlite3.connect(results[0]["path"]) as db:
                self.assertEqual(db.execute("SELECT ordinal,value_text FROM numeric_cells ORDER BY ordinal").fetchall(),[(1,"12.30"),(2,"-5.5")])
            with sqlite3.connect(results[1]["path"]) as db:
                self.assertEqual(db.execute("SELECT ordinal,value_text FROM numeric_cells").fetchall(),[(4,"4")])
            self.assertTrue(all(r["summary"]["whole_member_reconciled"] for r in results))
    def test_partition_plan(self):
        for form,total in m.storage.LARGE_NUMERIC_ROWS.items():m.validate_plan(m.scope_plan(form),total)
        for plan in [[("a",1,2),("b",2,4)],[("a",1,2),("b",4,4)],[("a",1,3)]]:
            with self.assertRaises(ValueError):m.validate_plan(plan,4)
    def test_prior_report_counts_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/"source.zip";i=root/"index.sqlite3"
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("FORM_RPT.csv","1,x\n")
                z.writestr("FORM_NMRC.csv","1,A000000,1,1,1\n")
                z.writestr("FORM_ALPHA.csv","1,A000000,1,1,x\n")
            prior=idx.project(p,i)
            with sqlite3.connect(i) as db:db.execute("UPDATE reports SET numeric_rows=2")
            with self.assertRaises(ValueError):m.project(p,i,prior,[("p1",1,1)],root)

    def test_hospital_annual_index_shape(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/"source.zip";i=root/"index.sqlite3"
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("FORM_2024_rpt.csv","1,private header\n")
                z.writestr("FORM_2024_nmrc.csv","1,A000000,00100,00100,12.30\n")
                z.writestr("FORM_2024_alpha.csv","1,A000000,00100,00100,secret alpha\n")
            prior=idx.project(p,i)
            self.assertEqual(set(prior["annual_partitions"]),{"2024"})
            result=m.project(p,i,prior,[("p1",1,1)],root)
            self.assertEqual(result[0]["summary"]["stored_rows"],1)
            with sqlite3.connect(result[0]["path"]) as db:
                self.assertEqual(db.execute("SELECT source_year,ordinal,value_text FROM numeric_cells").fetchall(),[("2024",1,"12.30")])
