import unittest
from pecos_label_reconciliation import classify,structure,audit,REH_ALT
class Tests(unittest.TestCase):
    def test_exact_reh_variant(self):
        self.assertEqual(classify("00-24",REH_ALT),"00-24|documented_general_dictionary_variant")
        self.assertEqual(classify("00-24","PART A PROVIDER - RURAL EMERGENCY HOSPITAL"),"00-24|matches")
        self.assertEqual(classify("00-09",REH_ALT),"00-09|label_differs")
    def test_structure(self):
        self.assertEqual(structure(" LLC "),"candidate_variant:LIMITED LIABILITY COMPANY")
        self.assertEqual(structure(""),"blank")
        self.assertEqual(structure("unknown arbitrary text"),"other_unreviewed")
    def test_prior_reconciliation(self):
        prior={"retained":1,"provider_code_label_states":{"":{"00-24|label_differs":1}}}
        r=audit("hospital-enrollment",[{"PROVIDER TYPE CODE":"00-24","PROVIDER TYPE TEXT":REH_ALT,"ORGANIZATION TYPE STRUCTURE":"LLC","PROPRIETARY NONPROFIT":"P"}],prior)
        self.assertEqual(r["provider_code_label_states"][""],{"00-24|documented_general_dictionary_variant":1})
