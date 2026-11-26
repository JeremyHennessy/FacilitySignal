import tempfile,unittest
from pathlib import Path
import openpyxl
from scripts.audit_qcor_key_shapes import inspect,shape
class QCORKeyShapeTests(unittest.TestCase):
    def test_only_shape_is_retained(self):
        self.assertEqual(shape("01AB23"),"text:99AA99")
        self.assertEqual(shape("12345"),"text:99999")
        self.assertEqual(shape(None),"null")
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"test.xlsx";book=openpyxl.Workbook();s=book.active
            s.append(["CCN","Facility Name","Survey Event ID","Survey Date","Deficiency Tag","Deficiency Tag Type"])
            for key in ("011300","01AB23","12345",None):
                s.append([key,"Synthetic Name","ABCD11","2024-01-01","J0001","Standard"])
            book.save(path);book.close()
            a=inspect(path)
            self.assertEqual((a["input_rows"],a["accepted_key_rows"],a["rejected_key_rows"]),(4,1,3))
            self.assertEqual(a["rejected_key_shape_counts"],{"text:99AA99":1,"text:99999":1,"null":1})
            self.assertNotIn("01AB23",str(a));self.assertNotIn("Synthetic Name",str(a))
