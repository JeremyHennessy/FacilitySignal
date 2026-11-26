import csv,io,unittest
from scripts.qualify_hrsa_sites import audit,norm,resolve
class HrsaTests(unittest.TestCase):
    def test_privacy_and_reconciliation(self):
        f=io.StringIO();w=csv.writer(f)
        h=["BPHC Assigned Number","Site Address","Site Postal Code","Site Type","Location Setting","Site State","Site Status","Site Name"]
        w.writerow(h)
        w.writerows([["1","Street","12345","Service","Clinic","NY","Active","Example clinic"],
                     ["2","","","Service","Clinic","NY","Active","Excluded"],
                     ["3","Street","12345","Service","Shelter","NY","Active","Protected"],
                     ["4","Street","12345","Service","Clinic","NY","Active","Domestic violence program"],
                     ["1","Street","12345","Service","Clinic","NY","Active","Duplicate"]])
        a=audit(f.getvalue().encode(),{norm(x) for x in h})
        self.assertTrue(a["mapping_complete"])
        self.assertEqual((a["input_rows"],a["privacy_screened_rows"],a["excluded_protected_or_incomplete_rows"],a["duplicate_site_id"]),(5,1,3,1))
        self.assertNotIn("Example clinic",str(a));self.assertNotIn("12345",str(a))
    def test_missing_mapping_fail_closed(self):
        a=audit(b"Site Name,Site State\nExample,NY\n",set())
        self.assertFalse(a["mapping_complete"]);self.assertEqual(a["privacy_screened_rows"],0)
