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

    def test_publisher_punctuation_and_unrecognized_header_suppression(self):
        f=io.StringIO();w=csv.writer(f)
        h=["BPHC Assigned Number","Site Address","Site Postal Code","Site Type","Location Setting","Site State","Site Status","Grantee’s organization type: (optional)"]
        w.writerow(h);w.writerow(["1","Street","12345","Service","Clinic","NY","Active","Other"])
        a=audit(f.getvalue().encode(),{norm(x) for x in h})
        self.assertTrue(a["mapping_complete"]);self.assertEqual(a["privacy_screened_rows"],1)
        self.assertEqual(a["metadata_exact_header_matches"],8)
        b=audit(b"Unverified label,Another label\nExample,Other\n",set())
        self.assertFalse(b["mapping_complete"]);self.assertEqual(b["headers"],[])

    def test_invalid_header_structural_evidence_only(self):
        f=io.StringIO();w=csv.writer(f)
        w.writerow(["Site Name","Site State",""]);w.writerow(["Example","NY",""]);w.writerow(["Other","CA",""])
        a=audit(f.getvalue().encode(),set())
        self.assertFalse(a["mapping_complete"]);self.assertEqual(a["input_rows"],2)
        self.assertEqual(a["headers"],[]);self.assertEqual(a["header_structure"]["invalid_columns"],[{"column_ordinal":3,"length":0,"reasons":["empty_or_no_ascii_alphanumeric"]}])
        self.assertEqual(a["header_structure"]["invalid_column_nonblank_counts"],{})
        self.assertEqual(a["privacy_screened_rows"],0)
        self.assertNotIn("Example",str(a))

    def test_single_empty_final_header_preflight(self):
        h=["BPHC Assigned Number","Site Address","Site Postal Code","Site Type","Location Setting","Site State","Site Status"]
        rows=[["1","Street","12345","Service","Clinic","NY","Active"],["2","Street","12345","Service","Clinic","NY","Active",""]]
        f=io.StringIO();w=csv.writer(f);w.writerow(h+[""]);w.writerows(rows)
        a=audit(f.getvalue().encode(),set())
        self.assertTrue(a["mapping_complete"]);self.assertEqual(a["privacy_screened_rows"],2)
        self.assertEqual(a["header_repair"]["row_width_counts"],{"7":1,"8":1})
        for invalid in (rows[0]+["unexpected"],rows[0][:-1],rows[0]+["",""]):
            f=io.StringIO();w=csv.writer(f);w.writerow(h+[""]);w.writerow(invalid)
            a=audit(f.getvalue().encode(),set())
            self.assertFalse(a["mapping_complete"]);self.assertEqual(a["privacy_screened_rows"],0)
            self.assertEqual(a["header_repair"]["unexpected_width_or_nonempty_extra_rows"],1)

    def test_observed_publisher_labels_and_suppression(self):
        h=["BPHC Assigned Number","Site Address","Site Postal Code","Health Center Location Type Description","Health Center Service Delivery Site Location Setting Description","Site State Abbreviation","Site Status Description"]
        f=io.StringIO();w=csv.writer(f);w.writerow(h+[""])
        w.writerows([["1","Example Street","12345","Service","Clinic","NY","Active"],
                     ["2","Suppressed","12345","Service","Clinic","NY","Active"],
                     ["3","Example Street","Not Available","Service","Clinic","NY","Active"],
                     ["4","Example Street","12345","Service","Domestic Violence Shelter","NY","Active"]])
        a=audit(f.getvalue().encode(),{norm(x) for x in h})
        self.assertTrue(a["mapping_complete"])
        self.assertEqual(a["privacy_screened_rows"],1)
        self.assertEqual(a["excluded_protected_or_incomplete_rows"],3)
        self.assertEqual(a["header_repair"]["row_width_counts"],{"7":4})
        self.assertNotIn("Example Street",str(a))
