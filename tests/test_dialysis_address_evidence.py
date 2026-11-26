import unittest
from dialysis_address_evidence import street,detail,audit
class Tests(unittest.TestCase):
    def test_suffix(self):
        self.assertEqual(street("12 Main Street"),street("12 Main St."))
        self.assertEqual(street("12 Main Street North"),street("12 Main St N"))
    def test_preserve_differences(self):
        for a,b in [("12 Main St Apt 1","12 Main St Apt 2"),("12 Main St","13 Main St"),("12-14 Main St","1214 Main St"),("12 Main St N","12 Main St S"),("1.2 Main St","12 Main St")]:
            self.assertNotEqual(street(a),street(b))
    def test_detail(self):
        p={"state":"NY","city":"Albany","zip":"12201","address":"12 Main Street"}
        r={"state_cd":"NY","city_name":"ALBANY","zip_cd":"12201-1234","st_adr":"12 Main St."}
        self.assertEqual(detail(p,r),("equal","equal","equal","suffix_or_terminal_direction"))
        out=audit([{**r,"prvdr_type_id":"07","prvdr_num":"123456"}],{"123456":p})
        self.assertEqual(out["prior_dispositions"],{"address_evidence_disagrees":1})
        self.assertEqual(out["normalization_diagnostic"],{"formatting_candidate_suffix_or_terminal_direction":1})
    def test_duplicate_not_promoted(self):
        p={"state":"NY","city":"Albany","zip":"12201","address":"12 Main Street"}
        r={"state_cd":"NY","city_name":"ALBANY","zip_cd":"12201","st_adr":"12 Main St.","prvdr_type_id":"07","prvdr_num":"123456"}
        out=audit([r,r],{"123456":p})
        self.assertEqual(out["prior_dispositions"],{"multiple_esrd_identifier_candidates":1})
        self.assertEqual(out["normalization_diagnostic"],{})
