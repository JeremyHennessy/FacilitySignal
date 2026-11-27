import json
import unittest
from scripts.review_cms_hpt_notice_identity import aggregate, classify

DIR=[{"ccn":"110001","address":"10 Sample Drive","city":"EXAMPLE","state":"AA","zip":"00001"}]
NOTICE={"identifier_label":"CCN","identifier_value":"110001","address":"10 Sample Dr","city":"Example",
        "state":"AA","zip":"00001-1234"}

class IdentityReview(unittest.TestCase):
    def test_exact_label_and_location_are_both_needed(self):
        self.assertEqual(classify(NOTICE,DIR),"review_candidate_explicit_ccn_and_unique_address")
        for fake in ("Reference Number","Unique Case Number",None):
            self.assertEqual(classify({**NOTICE,"identifier_label":fake},DIR),
                             "missing_explicit_ccn_unique_address_candidate")
        for key,value in (("state","BB"),("address","10 Sample Drive NE"),("zip","00002")):
            self.assertEqual(classify({**NOTICE,key:value},DIR),"explicit_ccn_address_not_corroborated")
        self.assertEqual(classify(NOTICE,DIR+DIR),"explicit_ccn_absent_or_ambiguous_in_directory")
        self.assertEqual(classify({**NOTICE,"identifier_value":110001},DIR),"unsupported_explicit_ccn")
        self.assertEqual(classify(NOTICE,DIR+[{**DIR[0],"ccn":"110002"}]),"explicit_ccn_address_not_corroborated")

    def test_same_row_documents_do_not_inherit_identifier(self):
        s=aggregate([NOTICE,{**NOTICE,"identifier_label":None}],DIR)
        self.assertEqual(s["notices_checked"],2)
        self.assertEqual(s["linkage_review_counts"],{"review_candidate_explicit_ccn_and_unique_address":1,
                                                      "missing_explicit_ccn_unique_address_candidate":1})
        self.assertEqual(s["canonical_provider_links"],0)
        self.assertNotIn("110001",json.dumps(s))

if __name__=="__main__":
    unittest.main()
