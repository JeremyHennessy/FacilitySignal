import tempfile,unittest
from pathlib import Path
import openpyxl
from scripts.qualify_qcor_provider import inspect,map_header
class QCORProviderTests(unittest.TestCase):
    def test_projection_and_reconciliation(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"test.xlsx"
            b=openpyxl.Workbook();s=b.active
            s.append(["CCN","Facility Name","Survey Event ID","Survey Date","Deficiency Tag","Deficiency Tag Type","Statement of Deficiency Text (Part 1)"])
            s.append(["01C0001000","Synthetic","ABCD-H1","11/01/2024","Q0000","Memo","Not retained"])
            s.append(["01C0001000","Synthetic","ABCD-H1","11/01/2024","Q0100","Condition","Not retained"])
            s.append(["01C0001001","Synthetic","ABC123","2024-11-01",None,None,None])
            s.append(["01X0001000","Wrong source","ABC123","2024-11-01","Q0100","Condition",None])
            b.save(path);b.close()
            a=inspect(path,"asc")
            self.assertEqual((a["input_rows"],a["stored_rows"],a["rejected_rows"]),(4,3,1))
            self.assertEqual(a["row_kinds"],{"memo":1,"nonmemo_tag":1,"no_tag_reported":1})
            self.assertEqual((a["distinct_survey_event_keys"],a["events_without_nonmemo_tag"]),(2,1))
            self.assertNotIn("Synthetic",str(a));self.assertNotIn("01C0001000",str(a))
            self.assertNotIn("Not retained",str(a))
    def test_header_ambiguity(self):
        with self.assertRaises(ValueError):map_header(["CCN","CCN"])
