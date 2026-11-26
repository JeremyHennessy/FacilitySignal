import csv
import io
import unittest
from citation_dictionary import HEADER,lookup,match,status_bucket

class CitationDictionaryTests(unittest.TestCase):
    def test_dictionary_cardinality_and_literal_match(self):
        s=io.StringIO();w=csv.writer(s);w.writerow(HEADER)
        w.writerows([["K","0123","K-0123","Synthetic text","Synthetic category"],
                     ["K","0123","K-0123","Other text","Synthetic category"],
                     ["F","0123","F-0123","Third text","Other category"]])
        entries,stats=lookup(s.getvalue().encode(),3)
        self.assertEqual(stats["distinct_keys"],2);self.assertEqual(stats["multi_definition_keys"],1)
        self.assertEqual(match(entries,"K123","Synthetic text","Synthetic category"),"exact_text_multiple_definitions")
        self.assertEqual(match(entries,"F0123","Third text","Other category"),"exact_text_single_definition")
        self.assertEqual(match(entries,"K0123","Other text","Other category"),"category_differs")
        self.assertEqual(match(entries,"K0123","unknown","Synthetic category"),"description_differs")
        self.assertEqual(match(entries,"E0123","x","y"),"key_missing")
        self.assertEqual(match(entries,"invalid","x","y"),"invalid_key")
        with self.assertRaises(ValueError):lookup(s.getvalue().encode(),4)
    def test_bad_combined_key_rejected(self):
        s=io.StringIO();w=csv.writer(s);w.writerow(HEADER);w.writerow(["K","0123","F-0123","text","category"])
        with self.assertRaises(ValueError):lookup(s.getvalue().encode(),1)
    def test_status_candidates_not_promoted(self):
        self.assertEqual(status_bucket("Deficient, Provider has no plan of correction"),"candidate_no_plan")
        self.assertEqual(status_bucket("Past Non-Compliance"),"source_reports_past_noncompliance")
        self.assertEqual(status_bucket("unreviewed source text"),"unresolved_other")
