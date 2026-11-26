import unittest
from scripts.audit_mqsa_identity import index_rows,match
class MQSAIdentityTests(unittest.TestCase):
    def test_separate_candidate_classes(self):
        a={"ccn":"000001","name":"Fixture Hospital","address":"1 Main St","city":"Town","state":"NY","zip":"00123"}
        b={**a,"ccn":"000002","name":"Other Clinic","address":"2 Main St"}
        idx=index_rows([("hospital",a),("hospital",b)])
        self.assertEqual(match({**a,"name":"fixture   hospital","zip":"00123-0000"},idx)[0],"name_and_address_text_single")
        self.assertEqual(match({**a,"address":"2 Main St"},idx)[0],"name_and_address_candidates_disagree")
        self.assertEqual(match({**a,"name":"different"},idx)[0],"address_city_zip_state_only")
        self.assertEqual(match({**a,"address":"Elsewhere"},idx)[0],"name_state_only")
        self.assertEqual(match({**a,"state":"AE"},idx)[0],"out_of_jurisdiction")
        self.assertEqual(match({**a,"state":"CA"},idx)[0],"no_exact_candidate")
