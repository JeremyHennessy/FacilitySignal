import tempfile,unittest,zipfile
from pathlib import Path
from scripts import archive_epa_program_coverage as m
class EPAProgramCoverageTests(unittest.TestCase):
    def test_rcra_composite_key_and_aggregate_only(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"source.zip";scope=m.SCOPES["rcra"]
            with zipfile.ZipFile(p,"w") as z:
                z.writestr(scope["naics"],"ID_NUMBER,ACTIVITY_LOCATION,NAICS_CODE\nNY1234567890,NY,622110\nNY1234567890,CA,621111\nCA1234567890,CA,624120\n")
                z.writestr(scope["facility"],"ID_NUMBER,ACTIVITY_LOCATION\nNY1234567890,NY\nCA1234567890,CA\n")
                for table in set(scope["tables"])-{scope["naics"],scope["facility"]}:z.writestr(table,"ID_NUMBER,ACTIVITY_LOCATION\nNY1234567890,NY\nNY1234567890,CA\n")
            s=m.qualify("rcra",p)
            self.assertEqual(s["source_rows_screened"],11);self.assertEqual(s["resolved_sector62_program_keys"],2)
            self.assertEqual(s["unresolved_sector62_program_keys"],1);self.assertEqual(s["resolved_healthcare_621_623_program_keys"],1)
            self.assertNotIn("NY1234567890",str(s));self.assertEqual(s["event_rows_retained"],0)
    def test_npdes_key_alias_is_exact(self):
        self.assertEqual(m.key_for("npdes",{"NPDES_ID":"NY0000001"}),m.key_for("npdes",{"EXTERNAL_PERMIT_NMBR":"NY0000001"}))
        self.assertIsNone(m.key_for("npdes",{"NPDES_ID":""}))
