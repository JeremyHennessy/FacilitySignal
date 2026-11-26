from datetime import date
import unittest
from scripts.postacute_raw_domain_audit import owner, cert_date, region_state, STATE_REGION, hha_reconciliation, audit_rows

class PostacuteRawDomainTests(unittest.TestCase):
    def test_ownership(self):
        labels=["For Profit","Non-Profit","Government"]
        self.assertEqual(owner("FOR PROFIT",labels),("casefold_match","For Profit"))
        self.assertEqual(owner("For-Profit",labels),("punctuation_candidate","For Profit"))
        self.assertEqual(owner("-",labels),("dash",None))
        self.assertEqual(owner("unknown owner value",labels),("unmapped",None))
    def test_date(self):
        r=date(2026,11,20)
        self.assertEqual(cert_date("2/29/2024",r),"valid_calendar_date")
        self.assertEqual(cert_date("2/29/2025",r),"calendar_review")
        self.assertEqual(cert_date("11/21/2026",r),"after_release")
        self.assertEqual(cert_date("-",r),"dash")
    def test_region(self):
        self.assertEqual(len(STATE_REGION),56)
        for state,region in (("DC",3),("PR",2),("VI",2),("AS",9),("GU",9),("MP",9),("AK",10)):
            self.assertEqual(region_state(state,str(region)),"matches_reference")
        self.assertEqual(region_state("NY","3"),"region_mismatch")
        self.assertEqual(region_state("XX","2"),"unknown_jurisdiction")
        self.assertEqual(region_state("NY","02"),"region_value_review")
    def test_prior_hha(self):
        r=hha_reconciliation()
        self.assertEqual(r["rows"],12409)
        self.assertEqual(r["casefold_qualified_categories"],{"Government Operated":239,"Non-Profit":1049,"Proprietary":8954})
        self.assertEqual(r["missing_dash"],2167)
        self.assertEqual(r["new_downloads"],0)
        self.assertFalse(r["exact_raw_spelling_retained"])
    def test_fixture_no_contact_or_identity_output(self):
        identity={"ccn":"123456","name":"SENSITIVE_FIXTURE_NAME","address":"SENSITIVE_ADDRESS","city":"CITY","state":"NY","zip":"12345"}
        row={"CMS Certification Number (CCN)":"123456","ZIP Code":"12345","Ownership Type":"UNKNOWN_SECRET","Certification Date":"1/1/2025","State":"NY","CMS Region":"2","Address Line 2":"-","Telephone Number":"SENSITIVE_PHONE"}
        rows={("123456","NY"):(row,identity)}
        spec={"fields":[{}]*10+[{"documented_domain":["For Profit"]},{}]}
        pin={"key":"hospice","release":"2026-11-20","sha256":"a"*64}
        shard={"source":"hospice","release":pin["release"],"row_count":1,"records":[{**identity,"capacity":""}]}
        r=audit_rows(rows,spec,pin,shard)
        self.assertEqual(r["identity_projection_parity"],1)
        self.assertEqual(r["ownership_unmapped_distinct"],1)
        self.assertEqual(r["telephone_presence_only"],{"nonblank":1})
        self.assertNotIn("SENSITIVE",str(r))
        self.assertNotIn("UNKNOWN_SECRET",str(r))
        self.assertNotIn("123456",str(r))
        with self.assertRaises(ValueError):
            audit_rows(rows,spec,pin,{**shard,"records":[{**identity,"city":"different","capacity":""}]})
