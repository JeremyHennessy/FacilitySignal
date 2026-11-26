import csv,io,sqlite3,unittest
from scripts.qualify_hospital_cost import CORE,MEASURES,number,calendar,project,select,TITLE,API,UUID

class HospitalCostTests(unittest.TestCase):
    def test_decimal_and_dates(self):
        self.assertEqual(number("-1.25"),("-1.25","negative"))
        self.assertEqual(number("0.00"),("0.00","zero"))
        self.assertEqual(number("Not Available"),(None,"missing_token"))
        self.assertEqual(number("1,000"),(None,"unrecognized"))
        self.assertEqual(calendar("01/02/2024"),(None,"ambiguous"))
        self.assertEqual(calendar("12/31/2024")[1],"mdy_only")
        self.assertEqual(calendar("2024-02-30"),(None,"invalid"))
    def test_report_grain_and_reconciliation(self):
        h=CORE+MEASURES+["Hospital Name"]
        f=io.StringIO();w=csv.writer(f);w.writerow(h)
        vals=["123.45"]*len(MEASURES)
        w.writerow(["1","012345","NY","2024-01-01","2024-12-31",*vals,"Synthetic Name"])
        w.writerow(["2","012345","NY","01/02/2024","12/31/2024",*vals,"Synthetic Name"])
        w.writerow(["2","012345","NY","01/02/2024","12/31/2024",*vals,"Synthetic Name"])
        with sqlite3.connect(":memory:") as db:
            a=project(f.getvalue().encode(),3,len(h),h,db,{"012345":{"NY"}})
            self.assertEqual(a["stored_rows"],2)
            self.assertEqual(a["reject_reasons"],{"duplicate_report_key":1})
            self.assertEqual(a["ccns_with_multiple_reports"],1)
            self.assertEqual(a["link_counts"],{"same_state":2})
            self.assertEqual(a["measure_value_states"]["Fixed Equipment"],{"positive":2})
            self.assertNotIn("Synthetic Name",str(a))
            self.assertNotIn("012345",str(a))
    def test_catalog_pinned_version(self):
        d={"dataset":[{"title":TITLE,"accessLevel":"public","distribution":[
            {"format":"API","accessURL":API,"temporal":"2024-01-01/2024-12-31"},
            {"format":"CSV","downloadURL":"https://data.cms.gov/sites/default/files/test.csv","temporal":"2024-01-01/2024-12-31"}]}]}
        self.assertEqual(select(d)["version"],UUID)
        d["dataset"][0]["accessLevel"]="restricted"
        with self.assertRaises(ValueError):select(d)
