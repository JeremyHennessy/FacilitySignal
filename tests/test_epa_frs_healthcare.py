import tempfile,unittest,zipfile
from pathlib import Path
from scripts import archive_epa_frs_healthcare as m
class FRSHealthcareTests(unittest.TestCase):
    def test_reported_sectors_and_join_grain(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/"source.zip"
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("FRS_FACILITIES.csv","REGISTRY_ID,FAC_STATE,FAC_NAME\n110000000001,NY,private name\n110000000002,CA,private name\n110000000003,TX,private name\n")
                z.writestr("FRS_NAICS_CODES.csv","REGISTRY_ID,NAICS_CODE,PGM_SYS_ACRNM,PGM_SYS_ID\n110000000001,622110,TEST,A\n110000000001,621111,TEST,A\n110000000002,624120,TEST,B\n110000000004,623110,TEST,C\n110000000003,111110,TEST,D\n")
                z.writestr("FRS_PROGRAM_LINKS.csv","REGISTRY_ID,PGM_SYS_ACRNM,PGM_SYS_ID\n110000000001,TEST,A\n110000000001,TEST,B\n110000000002,TEST,C\n110000000003,TEST,D\n")
            r=m.qualify(p,root/"scratch.sqlite3")
            self.assertEqual(r["source_rows_screened"],12)
            self.assertEqual(r["distinct_sector62_registry_ids_in_naics"],3)
            self.assertEqual(r["resolved_sector62_registry_ids"],2)
            self.assertEqual(r["resolved_healthcare_621_623_registry_ids"],1)
            self.assertEqual(r["unresolved_sector62_registry_ids"],1)
            self.assertEqual(r["distinct_health_sector_registry_program_pairs"],2)
            self.assertEqual(r["site_or_system_rows_retained"],0)
            self.assertNotIn("110000000001",str(r))
