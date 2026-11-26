import unittest
from remaining_raw_field_profile import AuditField, limited
class RemainingRawFieldProfileTests(unittest.TestCase):
    def test_restricted_no_value_output(self):
        f=AuditField("hospital-owner","FIRST NAME - OWNER")
        for v in ("example personal name","",None):f.add(v)
        result=f.result(3)
        self.assertEqual(result["presence"],{"nonblank":1,"blank":2})
        self.assertNotIn("example personal name",str(result))
        self.assertIsNone(f.base)
    def test_narrative_presence(self):
        f=AuditField("qcor-hospital","Statement of Deficiency Text (Part 1)")
        f.add("Synthetic narrative");f.add(None)
        self.assertEqual(f.result(2)["presence"],{"nonblank":1,"blank":1})
    def test_beds_candidate_zero_distinct_from_missing(self):
        f=AuditField("long-term-hospital","Total Number of Beds")
        for v in ("100","0","","Not Available","-1"):f.add(v)
        r=f.result(5)["header_quantity_candidate"]
        self.assertEqual(r["counts"],{"nonnegative_integer":2,"explicit_zero":1,"blank":1,"literal_marker":1,"other_token":1})
        self.assertEqual(r["range_and_sum"],{"min":0,"max":100,"sum":100})
    def test_service_indicator(self):
        f=AuditField("hospital","Emergency Services")
        for v in ("Yes","No","N/A","?",""):f.add(v)
        self.assertEqual(f.result(5)["literal_yes_no_counts"],{"yes":1,"no":1,"literal_marker":1,"other_token":1,"blank":1})
if __name__=="__main__":unittest.main()
