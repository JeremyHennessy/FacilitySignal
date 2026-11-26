import csv,io,sqlite3,unittest
from scripts.qualify_nursing_surveys import DATES,SUMMARY,SUMMARY_COUNTS,project,numeric_count,parse_date
def data(h,rows):
    f=io.StringIO();w=csv.writer(f);w.writerow(h);w.writerows(rows);return f.getvalue().encode()
class NursingSurveyTests(unittest.TestCase):
    def test_date_grain_and_duplicates(self):
        row=["012345","2024-01-01","Health Standard","1","2026-10-01"]
        other=["999999","2024-01-01","Infection Control","2","2026-10-01"]
        bad=["012345","2026-11-01","Health Standard","1","2026-10-01"]
        with sqlite3.connect(":memory:") as db:
            a=project("dates",data(DATES,[row,row,other,bad]),4,db,{"012345":{"NY"}})
            self.assertEqual((a["stored_rows"],a["rejected_rows"],a["exact_duplicate_source_rows"],a["repeated_candidate_key_rows"]),(3,1,1,1))
            self.assertEqual(a["link_counts"],{"ccn_present":2,"unmatched_ccn":1})
            self.assertNotIn("012345",str(a))
    def test_summary_unknown_is_not_zero(self):
        head=["012345","Synthetic Name","Synthetic Address","City","NY","10000","1","2024-01-01","",""]
        row=head+["0",""]+["2"]*(len(SUMMARY_COUNTS)-2)+["Ignored","2026-10-01"]
        with sqlite3.connect(":memory:") as db:
            a=project("summary",data(SUMMARY,[row]),1,db,{"012345":{"NY"}})
            self.assertEqual(a["link_counts"],{"same_state":1})
            self.assertEqual(db.execute("SELECT health_count,fire_count FROM survey_summary").fetchone(),(0,None))
            self.assertNotIn("Synthetic Name",str(a))
            self.assertEqual(a["count_field_value_states"][SUMMARY_COUNTS[1]],{"blank":1})
    def test_guards(self):
        self.assertEqual(numeric_count(""),(None,"blank"))
        self.assertEqual(numeric_count("2.00"),(2,"positive"))
        for v in ("-1","2.5","garbage"):
            with self.assertRaises(ValueError):numeric_count(v)
        with self.assertRaises(ValueError):parse_date("2026-11-01")
