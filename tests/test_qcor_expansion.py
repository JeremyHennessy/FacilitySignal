import tempfile,unittest
from pathlib import Path
import openpyxl
from scripts.qualify_qcor_expansion import resolve_download,provider_key,inspect,classify

class QCORExpansionTests(unittest.TestCase):
    def test_publisher_link_scope(self):
        html='<a href="/downloadCAH2567">Download full CAH 2567 dataset (Excel/XLSX)</a>'
        self.assertEqual(resolve_download(html,"cah"),"https://qcor.cms.gov/downloadCAH2567")
        for invalid in (html.replace("/downloadCAH2567","https://example.org/downloadCAH2567"),html.replace("CAH 2567","HHA 2567"),html+html.replace("/downloadCAH2567","/downloadOther2567")):
            with self.assertRaises(ValueError):resolve_download(invalid,"cah")
    def test_source_key_shape(self):
        self.assertEqual(provider_key(11300),"011300")
        self.assertEqual(provider_key("01L003"),"01L003")
        for code in ("A03401","B73975","C21823","D98500","E28900"):
            self.assertEqual(provider_key(code),code)
        for v in ("", "01L00300", "unknown", True,"E03401","E43401","F03401","A0L003","A0340X"):
            with self.assertRaises(ValueError):provider_key(v)
    def test_project_without_row_details(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"test.xlsx";b=openpyxl.Workbook();s=b.active
            s.append(["CCN","Facility Name","Survey Event ID","Survey Date","Deficiency Tag","Deficiency Tag Type","Statement of Deficiency Text"])
            s.append([11300,"Synthetic Site","ABCD-H1","11/01/2024","C0000","Memo","Not retained"])
            s.append(["011300","Synthetic Site","ABCD-H1","11/01/2024","C0100","Condition","Not retained"])
            s.append(["01L003","Synthetic Site","ABC123","2024-11-01",None,None,None])
            s.append(["bad","Synthetic Site","ABC123","2024-11-01","C0100","Condition",None])
            b.save(p);b.close()
            a=inspect(p,"cah")
            self.assertEqual((a["input_rows"],a["stored_rows"],a["rejected_rows"]),(4,3,1))
            self.assertEqual(a["row_kinds"],{"memo":1,"nonmemo_tag":1,"no_tag_reported":1})
            self.assertEqual((a["distinct_survey_event_keys"],a["events_without_nonmemo_tag"]),(2,1))
            for v in ("Synthetic Site","Not retained","011300","ABCD-H1"):self.assertNotIn(v,str(a))

    def test_icf_only_documented_tag_shape(self):
        m={"ccn":0,"event":1,"date":2,"tag":3,"kind":4}
        row=("01G001","ABCD11","2024-01-01","KS123","Standard")
        self.assertEqual(classify(row,m,"icf")[-1],"nonmemo_tag")
        self.assertEqual(classify((*row[:3],"KA123",row[4]),m,"icf")[-1],"nonmemo_tag")
        with self.assertRaisesRegex(ValueError,"tag_key_shape"):classify((*row[:3],"KA123",row[4]),m,"cah")
        with self.assertRaisesRegex(ValueError,"tag_key_shape"):classify(row,m,"cah")
        for tag in ("ZZ123","KS1234","K123X"):
            with self.assertRaisesRegex(ValueError,"tag_key_shape"):
                classify((*row[:3],tag,row[4]),m,"icf")
