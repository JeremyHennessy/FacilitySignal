import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
import collect_qcor_hospital as q
import facilitysignal as fs

class QCORTests(unittest.TestCase):
    def test_projection_ignores_narrative_and_preserves_id(self):
        data=[10001,"Fixture","Short Term","1 Test","City","AL","01001","Region","AB1234","01/02/2026","Standard","K0000","Initial comments","Memo","NEVER STORE ME",None,None,None]
        result=q.project(data)
        self.assertEqual(result[0],"010001")
        self.assertEqual(result[9],"2026-01-02")
        self.assertEqual(result[-1],"memo")
        self.assertNotIn("NEVER STORE ME",result)
        self.assertEqual(q.project(data[:14]),result)
        with self.assertRaisesRegex(ValueError,"wrong_column_count"): q.project(data+[None])
        data[8]=123
        with self.assertRaisesRegex(ValueError,"event_id"): q.project(data)

    @unittest.skipUnless(importlib.util.find_spec("openpyxl"),"xlsx dependency only in QCOR qualification")
    def test_transaction_and_populated_route(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/"test.xlsx";db=root/"data.sqlite3"
            book=openpyxl.Workbook();sheet=book.active;sheet.title=q.SHEET
            sheet.append(q.HEADER)
            sheet.append(["010001","Fixture","Short Term","1 Test","City","AL","01001","Region","AB1234","01/02/2026","Standard","K0521","HVAC","Standard","NEVER STORE ME",None,None,None])
            book.save(p);book.close()
            meta={"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"retrieved_at":"2026-11-25T00:00:00Z","bytes":p.stat().st_size}
            with self.assertRaisesRegex(ValueError,"qualification failed"):
                q.import_workbook(db,p,meta,2)
            with closing(fs.connect(db)) as conn:
                self.assertIsNone(fs.hospital_survey_search(conn,{})["release"])
            a=q.import_workbook(db,p,meta,1)
            self.assertEqual(a["survey_event_keys"],1)
            self.assertEqual(a["stored_rows"],1)
            with closing(fs.connect(db)) as conn:
                result=fs.hospital_survey_search(conn,{"ccn":"010001","tag":"K0521"})
                self.assertEqual(result["total"],1)
                self.assertNotIn("NEVER STORE ME",str(result))
                self.assertIn("HVAC",fs.render_hospital_surveys(conn,{}))
