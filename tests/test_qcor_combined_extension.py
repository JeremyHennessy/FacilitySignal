import hashlib, sqlite3, tempfile, unittest
from pathlib import Path
import openpyxl
from scripts.qualify_qcor_combined_extension import create_tables, project, verify_domain

class QCORCombinedTest(unittest.TestCase):
    def test_source_scoped_rows_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as t, sqlite3.connect(":memory:") as db:
            create_tables(db)
            header=["CCN","Survey Event ID","Survey Date","Deficiency Tag","Deficiency Tag Type","Statement of Deficiency Text"]
            def fixture(sid,ccn):
                path=Path(t)/(sid+".xlsx")
                b=openpyxl.Workbook();s=b.active;s.append(header)
                s.append([ccn,"E1","2025-01-02","C0000","Memo","DO NOT RETAIN"])
                s.append([ccn,"E1","2025-01-02","C0001","Standard","DO NOT RETAIN"])
                b.save(path);b.close()
                pin={"source_id":sid,"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"input_rows":2,"qualified_rows":2,"qualification_run":1}
                prior={"header":header,"field_mapping":dict(zip(("ccn","event","date","tag","kind"),header[:5])),
                       "input_rows":2,"stored_rows":2,"blank_rows":0,"rejected_rows":0,"row_kinds":{"memo":1,"nonmemo_tag":1},
                       "distinct_provider_keys":1,"distinct_survey_event_keys":1,"events_with_nonmemo_tag":1,"events_without_nonmemo_tag":0}
                return path,pin,prior
            a,p,q=fixture("FS-025","12C1234567")
            result=project(db,a,"asc",p,q);self.assertEqual(result["stored_rows"],2)
            b,p2,q2=fixture("FS-028","12X1234567")
            with self.assertRaises(ValueError):project(db,b,"xray",p2,{**q2,"stored_rows":3})
            self.assertEqual(db.execute("SELECT count(*) FROM qcor_extension").fetchone()[0],2)
            project(db,b,"xray",p2,q2)
            self.assertEqual(db.execute("SELECT count(*) FROM qcor_extension").fetchone()[0],4)
            self.assertNotIn("DO NOT RETAIN"," ".join(db.iterdump()))
    def test_icf_domain_hash(self):
        d={"KA001","KL001"};h=hashlib.sha256("\n".join(sorted(d)).encode()).hexdigest()
        p={"required_domain":{"code_count":2,"sorted_code_sha256":h}}
        self.assertEqual(verify_domain(d,p),h)
        with self.assertRaises(ValueError):verify_domain({"KA001","KL002"},p)
