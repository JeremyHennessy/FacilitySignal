import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from scripts.audit_epa_medical_identity import audit,match_bucket,norm,MEMBER

class EpaMedicalIdentityTests(unittest.TestCase):
    def test_candidate_boundaries(self):
        index={("NY","sample clinic"):{("hospital","000001"),("rehabilitation","000002")},("CA","other clinic"):{("nursing","000003")}}
        def row(k,n,s):return {"PWSID":k,"PWS_NAME":n,"STATE_CODE":s}
        for k,n,s,w in [
          ("NY1234567"," Sample  CLINIC ","NY","multiple_candidates"),
          ("CA1234567","Other Clinic","CA","one_candidate"),
          ("NY1234567","Sample Clinic","CA","no_exact_candidate"),
          ("NY1234567","Sample-Clinic","NY","no_exact_candidate"),
          ("AB12C3456","Sample Clinic","NY","unresolved_identifier"),
          ("NY1234567","","NY","missing_or_unsupported_name_state")]:
            self.assertEqual(match_bucket(row(k,n,s),index,{"NY","CA"})[0],w)
    def test_aggregate_no_row_values_and_duplicate_rejection(self):
        header=["PWSID","PWS_NAME","STATE_CODE","SERVICE_AREA_TYPE_CODE","SERVICE_AREA_TYPE_DESC","PWS_ACTIVITY_CODE"]
        rows=[["NY1234567","Secret Example","NY","MF","Medical Facility","A"],
              ["NY1234568","Secret Example","NY","MF","Medical Facility","I"],
              ["AB12C3456","Secret Example","NY","MF","Medical Facility","N"],
              ["NY1234569","Secret Example","NY","IN","Institution","A"]]
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"sample.zip"
            def make(data):
                s=io.StringIO();w=csv.writer(s);w.writerow(header);w.writerows(data)
                with zipfile.ZipFile(path,"w") as z:z.writestr(MEMBER,s.getvalue())
            make(rows);idx={("NY",norm("Secret Example")):{("hospital","000001")}}
            a=audit(path,idx,{"NY"})
            self.assertEqual(a["candidate_state_counts"],{"one_candidate":2,"unresolved_identifier":1})
            self.assertEqual(a["candidate_pairs"],2);self.assertEqual(a["distinct_cms_source_rows_in_candidates"],1)
            for value in ("Secret Example","NY1234567","AB12C3456","000001"):self.assertNotIn(value,str(a))
            make(rows+[rows[0]])
            with self.assertRaises(ValueError):audit(path,idx,{"NY"})
