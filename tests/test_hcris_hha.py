import csv,io,tempfile,unittest,zipfile
from pathlib import Path
from scripts.qualify_hcris_hha import resolve,inspect,cell_state,PAGE
class HCRISHHATests(unittest.TestCase):
    def test_resolve_official_link(self):
        a='<a href="/files/zip/hha20-2024.zip">HHA-2020 FY 2024 DATA FILES</a>'
        self.assertEqual(resolve(a),"https://www.cms.gov/files/zip/hha20-2024.zip")
        with self.assertRaises(ValueError):resolve(a.replace("/files/zip/","https://other.example/"))
    def test_relational_reconciliation(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"a.zip"
            with zipfile.ZipFile(path,"w") as z:
                z.writestr("HHA20_2024_RPT.csv","123,provider\n456,other\n")
                z.writestr("HHA20_2024_NMRC.csv","123,A000000,00001,00001,10.25\n456,A000000,00001,00001,-2\n999,A000000,00002,00001,0\n")
                z.writestr("HHA20_2024_ALPHNMRC.csv","123,S000000,00001,00001,SECRET\n")
            a=inspect(path)
            self.assertEqual(a["report"]["distinct_report_keys"],2)
            self.assertEqual(a["numeric"]["report_key_link_counts"],{"report_present":2,"orphan_report_key":1})
            self.assertEqual(a["numeric"]["value_states"],{"positive":1,"negative":1,"zero":1})
            self.assertEqual(a["alpha"]["reports_with_cells"],1)
            self.assertNotIn("SECRET",str(a))
    def test_value_shape(self):
        self.assertEqual(cell_state(""),"blank")
        self.assertEqual(cell_state("0.00"),"zero")
        self.assertEqual(cell_state("1,000"),"unrecognized")
