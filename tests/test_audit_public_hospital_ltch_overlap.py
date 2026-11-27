import json
import unittest
from scripts.audit_public_hospital_ltch_overlap import audit,cohort

def site(address,state="AA"):
    return {"address":address,"city":"Fixture","state":state,"zip":"00001"}

class CrossGrainTests(unittest.TestCase):
    def test_literal_formatting_true_difference_and_state_conflict(self):
        h={f"AB00{i}0":site("1 Example St") for i in range(4)}
        l={"AB0000":site("1 Example St"),"AB0010":site("1 Example St -"),
           "AB0020":site("1 Example St - Annex"),"AB0030":site("1 Example St","BB")}
        r=audit(h,l)
        self.assertEqual(r["same_ccn_candidates_by_address_state"],{
            "ccn_state_literal_site":1,"ccn_state_ltch_terminal_dash_only":1,
            "ccn_state_other_site_difference":1,"ccn_state_conflict":1})
        self.assertNotIn("Example",json.dumps(r))
        self.assertEqual(r["canonical_facility_or_location_merges"],0)

    def test_duplicate_identity_and_wrong_edition_fail_closed(self):
        record={"ccn":"AB0000",**site("1 Example St")}
        pack={"source":"hospital","release":"2026-11-12","row_count":2,"records":[record,record]}
        with self.assertRaises(ValueError):cohort(pack,2)
        with self.assertRaises(ValueError):cohort({**pack,"release":"2026-09-23"},2)

if __name__=="__main__":
    unittest.main()
