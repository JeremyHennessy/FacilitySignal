"""Regression coverage for non-generalized directional punctuation in FS-169."""
import unittest
from scripts.review_cms_hpt_notice_identity import classify

class DirectionalPunctuationTests(unittest.TestCase):
    def test_comma_suffix_and_dotted_prefix_are_not_normalized_into_matches(self):
        common={"city":"Fixture Town","state":"AA","zip":"00001"}
        for source, directory in (("10 Sample Road, NE","10 Sample Road, NE"),
                                  ("10 N.W. Sample Ave","10 NW Sample Ave")):
            with self.subTest(source=source):
                self.assertEqual(classify({**common,"address":source},[{**common,"address":directory}]),
                                 "missing_explicit_ccn_no_address_candidate")

if __name__=="__main__":
    unittest.main()
