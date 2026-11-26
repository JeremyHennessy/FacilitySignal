import tempfile,unittest,zipfile
from pathlib import Path
from scripts import archive_osha_enforcement_coverage as m
class OSHAEnforcementCoverageTests(unittest.TestCase):
    def test_source_row_and_activity_grains(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"inspection.zip";q=Path(d)/"violation.zip"
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("part1.csv","ACTIVITY_NR,NAICS_CODE,SITE_STATE,OPEN_DATE,INSP_SCOPE,ESTAB_NAME\n001,622110,NY,20250101,A,Private name\n001,622110,NY,20250101,A,Private name\n002,624120,CA,2025-02-01,D,Private name\n003,111110,CA,2025-02-01,A,Private name\n004,000000,NY,20250101,A,Private name\n")
            with zipfile.ZipFile(q,"w") as z:
                z.writestr("part1.csv","ACTIVITY_NR,CITATION_ID,DELETE_FLAG,VIOL_TYPE\n001,1,,S\n001,2,X,O\n002,1,D,W\n003,1,,S\n")
            ids,ins=m.inspect(p);v=m.violations(q,ids)
            self.assertEqual(ins["source_rows_screened"],5);self.assertEqual(ins["sector62_activity_keys"],2)
            self.assertEqual(ins["healthcare_621_623_activity_keys"],1)
            self.assertEqual(v["source_rows_screened"],4);self.assertEqual(v["matched_sector62_activity_keys"],2)
            self.assertEqual(v["matched_rows_by_delete_flag_literal"],{"blank":1,"X":1,"D":1})
            self.assertNotIn("Private name",str(ins));self.assertNotIn("001",str(v["matched_rows_by_delete_flag_literal"]))
    def test_conflicting_activity_codes_fail(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"inspection.zip"
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("part1.csv","ACTIVITY_NR,NAICS_CODE,SITE_STATE,OPEN_DATE,INSP_SCOPE\n1,622110,NY,20250101,A\n1,621111,NY,20250101,A\n")
            with self.assertRaises(ValueError):m.inspect(p)
