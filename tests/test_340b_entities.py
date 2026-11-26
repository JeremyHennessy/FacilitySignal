import tempfile,unittest
from pathlib import Path
import openpyxl
from scripts.qualify_340b_entities import inspect,participation,report_page,URL
class CoveredEntityTests(unittest.TestCase):
    def test_aggregate_only(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"sample.xlsx";b=openpyxl.Workbook();s=b.active;s.title="Covered Entities"
            s.append(["Export header"]);s.append(["340B ID","CE ID","Entity Type","Participating","Entity Name","Contact"])
            s.append(["SYN-001",1,"DSH",True,"Example organization","SECRET CONTACT"])
            s.append(["SYN-002",2,"CH",False,"Other organization","SECRET CONTACT"])
            s.append(["SYN-003",2,"CH",True,"Duplicate","SECRET CONTACT"])
            b.create_sheet("Shipping Addresses").append(["SECRET SHIPPING ADDRESS"])
            b.create_sheet("Contract Pharmacies").append(["SECRET PHARMACY"])
            b.save(path);b.close()
            a=inspect(path)
            self.assertEqual((a["input_rows"],a["stored_rows"],a["rejected_rows"]),(3,2,1))
            self.assertEqual(a["reject_reasons"],{"duplicate_ce_id":1})
            self.assertEqual(a["participation_counts"],{"publisher_true":1,"publisher_false":1})
            self.assertFalse(a["shipping_and_contract_pharmacy_sheets_parsed"])
            self.assertNotIn("SECRET",str(a));self.assertNotIn("SYN-001",str(a))
    def test_report_scope(self):
        self.assertTrue(report_page(URL))
        self.assertFalse(report_page(URL.replace("/Reports/","/Login/")))
        self.assertFalse(report_page(URL.replace("340bopais.hrsa.gov","example.org")))
        self.assertEqual(participation("Unknown"),"unrecognized")
