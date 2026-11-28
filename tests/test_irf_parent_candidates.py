import json
import unittest
from scripts import qualify_irf_parent_candidates as q

def row(token, state="AL", address="Synthetic street", name="Synthetic provider"):
    return {"ccn":token,"state":state,"address":address,"city":"Synthetic city","zip":"12345","name":name}

class IRFParentCandidates(unittest.TestCase):
    def test_numbering(self):
        for token, expected in [
            ("21T101",("T","210101")), ("21R301",("R","211301")),
            ("21TA26",("extended_A","212026")), ("21TB26",("extended_B","212126")),
            ("21TC26",("extended_C","212226")), ("21TE26",("extended_E","213326")),
            ("21TF26",("extended_F","214026")), ("21TK26",("extended_K","214426")),
            ("21TA126",("extended_nonstandard_length",None)), ("21TD26",("unresolved",None)),
            ("21T880",("T",None)), ("21R201",("unresolved",None)),
            ("213025",("numeric_rehab",None))]:
            self.assertEqual(q.candidate(token),expected)
    def test_evidence_not_inference(self):
        a=q.screen([row("21T101"),row("21T102"),row("21T103"),row("21T104"),row("21T105"),row("21T106")],
            [row("210101"),row("210102",address="Other"),row("210103",state="NY"),
             row("210104"),row("210104"),row("210105",name="Other")])
        self.assertEqual(a["counts"],{"same_state_address_name":1,"same_state_context_differs":1,
            "state_conflict":1,"multiple_directory_records":1,"same_state_address_name_differs":1,
            "no_directory_candidate":1})
        self.assertNotIn("210101",str(a))
        self.assertNotIn("Synthetic",str(a))
    def test_duplicate_fails(self):
        with self.assertRaises(ValueError):
            q.screen([row("21T101"),row("21T101")],[])
    def test_exact_pinned_projections(self):
        evidence=json.loads((q.ROOT/"research/fs043_irf_parent_candidate_audit_20261128.json").read_text())
        self.assertEqual(q.audit(),evidence["aggregate"])
