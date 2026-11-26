import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from scripts.audit_epa_medical_area import audit,area,MEMBER

class MedicalAreaTests(unittest.TestCase):
    def test_exact_and_unconfirmed_semantics(self):
        for c,d,w in (("MF","Medical Facility","exact_code_and_description"),("MF","Other","medical_code_description_unconfirmed"),("IN","Medical Facility","medical_description_code_unconfirmed"),("","Other","missing_code"),("MF;IN","Other","other_code"),("IN","Institution","other_code")):
            self.assertEqual(area(c,d),w)
    def fixture(self,path,rows):
        buf=io.StringIO();w=csv.writer(buf);w.writerow(["PWSID","SERVICE_AREA_TYPE_CODE","SERVICE_AREA_TYPE_DESC","PWS_ACTIVITY_CODE"]);w.writerows(rows)
        with zipfile.ZipFile(path,"w") as z:z.writestr(MEMBER,buf.getvalue())
    def test_unresolved_separation_and_no_keys_retained(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"sample.zip";self.fixture(path,[("NY1234567","MF","Medical Facility","A"),("AB12C3456","MF","Medical Facility","I"),("NY1234568","MF","Other","N"),("NY1234569","","","")])
            a=audit(path)
            self.assertEqual(a["source_rows"],4)
            self.assertEqual(a["area_counts"]["exact_code_and_description"],2)
            self.assertEqual(a["area_by_identifier_state"]["unresolved_format"],{"exact_code_and_description":1})
            self.assertEqual(a["exact_medical_area_activity_raw_code_counts"],{"A":1,"I":1})
            self.assertNotIn("AB12C3456",str(a));self.assertNotIn("NY1234567",str(a))
    def test_duplicate_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"sample.zip";self.fixture(path,[("NY1234567","MF","Medical Facility","A")]*2)
            with self.assertRaises(ValueError):audit(path)
