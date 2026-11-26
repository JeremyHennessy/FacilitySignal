import csv,io,sqlite3,unittest
from scripts.qualify_snf_cost import CORE,MEASURES,number,calendar,project,select,TITLE,PERIOD
API="https://data.cms.gov/data-api/v1/dataset/12345678-1234-1234-1234-123456789abc/data"
class SNFCostTests(unittest.TestCase):
    def test_catalog_period_and_scope(self):
        d={"dataset":[{"title":TITLE,"accessLevel":"public","distribution":[
            {"format":"API","accessURL":API,"temporal":PERIOD},
            {"format":"API","description":"latest","accessURL":API,"temporal":PERIOD},
            {"format":"CSV","downloadURL":"https://data.cms.gov/sites/default/files/test.csv","temporal":PERIOD}]}]}
        self.assertEqual(select(d)["api"],API)
        d["dataset"][0]["accessLevel"]="restricted"
        with self.assertRaises(ValueError):select(d)
    def test_report_grain_and_exact_decimal(self):
        h=CORE+MEASURES+["Facility Name"]
        f=io.StringIO();w=csv.writer(f);w.writerow(h)
        vals=["123.45"]*len(MEASURES)
        w.writerow(["1","012345","NY","2024-01-01","2024-12-31",*vals,"Synthetic Name"])
        w.writerow(["2","012345","NY","01/02/2024","12/31/2024",*vals,"Synthetic Name"])
        w.writerow(["2","012345","NY","01/02/2024","12/31/2024",*vals,"Synthetic Name"])
        with sqlite3.connect(":memory:") as db:
            a=project(f.getvalue().encode(),3,len(h),h,db,{"012345":{"NY"}})
            self.assertEqual((a["stored_rows"],a["rejected_rows"]),(2,1))
            self.assertEqual(a["link_counts"],{"same_state":2})
            self.assertEqual(a["ccns_with_multiple_reports"],1)
            self.assertEqual(a["measure_value_states"]["Contract Labor"],{"positive":2})
            self.assertNotIn("012345",str(a))
            self.assertNotIn("Synthetic Name",str(a))
    def test_numeric_and_date_guards(self):
        self.assertEqual(number("0.00"),("0.00","zero"))
        self.assertEqual(number("Not Available"),(None,"missing_token"))
        self.assertEqual(number("1,000"),(None,"unrecognized"))
        self.assertEqual(calendar("01/02/2024"),(None,"ambiguous"))
