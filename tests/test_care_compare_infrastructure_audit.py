import unittest
from care_compare_infrastructure_audit import audit,FIELDS
class AuditTests(unittest.TestCase):
    def test_dialysis_cross_tab(self):
        fields=list(FIELDS["dialysis"])+["# of Dialysis Stations"]
        result=audit("dialysis",fields,[["Yes","No","Yes","No","Yes","0"],["No","Yes","No","Yes","No","12"]])
        self.assertEqual(result["rows"],2)
        self.assertEqual(result["station_service_cross_tabs"]["Offers in-center hemodialysis"],{"zero | Yes":1,"positive | No":1})
    def test_missing_and_numeric(self):
        r=audit("long-term-hospital",list(FIELDS["long-term-hospital"]),[["12"],["Not Available"],[""]])
        self.assertEqual(r["literal_counts"]["Total Number of Beds"],{"positive":1,"Not Available":1,"<blank>":1})
    def test_row_width(self):
        with self.assertRaises(ValueError):audit("nursing",list(FIELDS["nursing"]),[["Yes"]])
    def test_reject_unexpected_token(self):
        with self.assertRaises(ValueError):audit("nursing",list(FIELDS["nursing"]),[["a"*41,"Y","N",""]])
