import sqlite3,unittest
from scripts.qualify_nppes_v2 import LABELS,REQUIRED,resolve,npi_valid,date_state,main_rows,ref_rows
class NPPESV2Tests(unittest.TestCase):
    def test_exact_publisher_link(self):
        html='<a href="/nppes/synthetic.zip">'+LABELS["weekly"]+'</a>'
        self.assertEqual(resolve(html,"weekly"),"https://download.cms.gov/nppes/synthetic.zip")
        with self.assertRaises(ValueError):resolve(html,"monthly")
        with self.assertRaises(ValueError):resolve(html.replace("/nppes/","https://example.org/nppes/"),"weekly")
    def test_checksum_and_exclusion(self):
        npi=next("123456789"+str(i) for i in range(10) if npi_valid("123456789"+str(i)))
        self.assertTrue(npi_valid(npi));self.assertFalse(npi_valid(npi[:-1]+str((int(npi[-1])+1)%10)))
        h=REQUIRED+["Healthcare Provider Taxonomy Code_"+str(i) for i in range(2,16)]+["Unretained field"]
        def row(entity,key,name,deactivated=""):
            d={"NPI":key,"Entity Type Code":entity,"Provider Organization Name (Legal Business Name)":name,"NPI Deactivation Date":deactivated,"Healthcare Provider Taxonomy Code_1":"123456789X"}
            return [d.get(k,"") for k in h]
        rows=[row("1","SECRET INDIVIDUAL","SECRET NAME"),row("2",npi,"Synthetic organization"),row("", "SECRET HISTORICAL","","01/01/2020")]
        with sqlite3.connect(":memory:") as db:
            a=main_rows(iter(rows),h,db,10)
            self.assertEqual(a["entity_classes"],{"individual_excluded":1,"organization":1,"untyped_with_deactivation":1})
            self.assertEqual(a["distinct_valid_organization_npis"],1)
            self.assertNotIn(npi,str(a));self.assertNotIn("SECRET",str(a))
            self.assertEqual(db.execute("SELECT count(*) FROM organizations").fetchone()[0],1)
            ref=ref_rows(iter([[npi,"SECRET ALTERNATE"],["9999999999","SECRET OTHER"]]),["NPI","ignored"],db,10)
            self.assertEqual(ref["key_counts"],{"type2_key_match":1,"outside_qualified_type2_scope":1})
            self.assertNotIn("SECRET",str(ref))
    def test_dates(self):
        self.assertEqual(date_state(""),"blank")
        self.assertEqual(date_state("02/29/2024"),"reported")
        self.assertEqual(date_state("02/29/2025"),"invalid")
