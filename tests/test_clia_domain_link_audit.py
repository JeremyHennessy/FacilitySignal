import unittest
from clia_domain_link_audit import domain,quantity,DOMAINS
class CLIADomainLinkTests(unittest.TestCase):
    def test_codes_exact(self):
        self.assertEqual(domain(" 00 ",DOMAINS["CURRENT_CLIA_LAB_CLSFCTN_CD"]),"00")
        self.assertEqual(domain("0",DOMAINS["CURRENT_CLIA_LAB_CLSFCTN_CD"]),"unrecognized")
        self.assertEqual(domain("9",DOMAINS["CRTFCT_TYPE_CD"]),"9")
        self.assertEqual(domain("9",DOMAINS["APLCTN_TYPE_CD"]),"unrecognized")
        self.assertEqual(domain("",DOMAINS["CRTFCT_TYPE_CD"]),"blank")
    def test_quantities_are_not_interpreted(self):
        self.assertEqual([quantity(x) for x in ("","0","10","-1","NA","1.5")],["blank","zero","positive","other","other","other"])
