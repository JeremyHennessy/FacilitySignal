import unittest
from scripts.probe_qcor_icf_tag_domain import analyze
class ICFDomainTests(unittest.TestCase):
    def test_only_tag_metadata(self):
        html='<select name="facility"><option value="SECRET"></option></select><select name="deficiencyTags"><option value=""></option><option value="KS123">a</option><option value="KA123">b</option><option value="KP456">c</option><option value="W0001">d</option></select>'
        domains,a=analyze(html)
        self.assertEqual(len(domains),1);self.assertEqual(a["tag_named_selectors"][0]["code_family_counts"],{"KA":1,"KP":1,"KS":1,"W":1})
        self.assertNotIn("SECRET",str(a));self.assertNotIn("KS123",str(a))
    def test_ambiguous_and_unknown_options(self):
        d,a=analyze('<select name="tags"><option value="KA123"></option><option value="KS123"></option><option value="unknown"></option></select>')
        self.assertEqual(d,[]);self.assertEqual(a["tag_named_selectors"][0]["other_option_count"],1)
