import tempfile
import unittest
from pathlib import Path
import openpyxl
from probe_iqies_dictionary import inspect

class IqiesDictionaryTests(unittest.TestCase):
    def test_exact_locations_missing_and_ambiguous(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.xlsx"
            w=openpyxl.Workbook();s=w.active;s.title="Dictionary"
            s.append(["Element","Definition","Domain"])
            s.append(["OPRTG_ROOM_CNT","Synthetic room definition","0-99"])
            s.append(["lab_srvc_cd","Synthetic service definition","Not Applicable"])
            s.append(["lab_srvc_cd","Second exact location",None])
            s.append(["other","contains procedure_room_cnt in prose",None])
            w.save(p);w.close()
            out=inspect(p,["oprtg_room_cnt","lab_srvc_cd","procedure_room_cnt"])
            self.assertEqual(out["matched_fields"],2)
            self.assertEqual(out["missing_fields"],["procedure_room_cnt"])
            self.assertEqual(out["ambiguous_fields"],["lab_srvc_cd"])
            self.assertEqual(out["field_locations"]["oprtg_room_cnt"][0]["row"],2)
            self.assertEqual(out["semantic_status"],"unreviewed")
    def test_invalid_workbook(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"invalid.xlsx";p.write_text("not workbook")
            with self.assertRaises(ValueError):inspect(p,["oprtg_room_cnt"])
