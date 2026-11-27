import csv
import io
import hashlib
import unittest
from scripts import qualify_ltch_provider_linkage as q

def payload(header, rows):
    s=io.StringIO(newline="")
    w=csv.DictWriter(s, fieldnames=header)
    w.writeheader()
    w.writerows(rows)
    return s.getvalue().encode()

def directory(ccn="012345", **updates):
    r=dict.fromkeys(q.DIRECTORY,"-")
    r.update({q.CCN:ccn,"Provider Name":"Example","Address Line 1":"Street",
              "City/Town":"City","State":"AL","ZIP Code":"01234"})
    r.update(updates)
    return r

def provider(ccn="012345", code="TEST_01", **updates):
    r={k:v for k,v in directory(ccn).items() if k in q.PROVIDER}
    r.update({"Measure Code":code,"Score":"not for analysis","Footnote":"-",
              "Start Date":"10/01/2024","End Date":"09/30/2025","Measure Date Range":"-"})
    r.update(updates)
    return r

class LTCHLinkage(unittest.TestCase):
    def run_screen(self,d,p):
        return q.screen(payload(q.DIRECTORY,d),payload(q.PROVIDER,p),len(d),len(p))

    def test_reconcile_grains_and_no_identifiers_or_scores_in_receipt(self):
        res=self.run_screen([directory(),directory("012346")],
                            [provider(),provider(code="TEST_02"),provider("012347")])
        self.assertEqual(res["exact_ccn_intersection"],1)
        self.assertEqual(res["directory_only_ccns"],1)
        self.assertEqual(res["provider_only_ccns"],1)
        self.assertEqual(res["observation_evidence_states"],{"same_state_exact_context":2,"unmatched_ccn":1})
        self.assertEqual(res["provider_evidence_states"],{"same_state_exact_context":1,"unmatched_ccn":1})
        self.assertNotIn("012345",str(res))
        self.assertNotIn("not for analysis",str(res))
        self.assertEqual(res["canonical_matches"],0)
        self.assertFalse(res["public_promotion"])

    def test_context_conflict_missing_and_mixed(self):
        p=[provider(),provider(code="TEST_02",State="NY"),
           provider("012346", **{"ZIP Code":"-"}),
           provider("012347", **{"Address Line 1":"Other"}),
           provider("012348",State="-")]
        res=self.run_screen([directory(ccn) for ccn in ["012345","012346","012347","012348"]],p)
        self.assertEqual(res["provider_evidence_states"],
          {"mixed_evidence":1,"same_state_context_missing":1,"same_state_context_differs":1,"state_unresolved":1})

    def test_duplicate_ccn_duplicate_measure_and_invalid_identifier_fail(self):
        for d,p in [([directory(),directory()],[provider()]),
                    ([directory()],[provider(),provider()]),
                    ([directory("12345")],[provider()])]:
            with self.assertRaises(ValueError):
                self.run_screen(d,p)

    def test_pinned_byte_and_release_gates(self):
        b=b"exact"
        pin={"bytes":len(b),"sha256":hashlib.sha256(b).hexdigest()}
        self.assertEqual(q.verify_bytes(b,pin),b)
        for x in (b"wrong", b"extra!", b""):
            with self.assertRaises(ValueError):
                q.verify_bytes(x,pin)
        p=q.pins()
        self.assertEqual((p["directory"]["rows"],p["provider"]["rows"]),(311,24258))

    def test_width_header_and_count_fail(self):
        d=payload(q.DIRECTORY,[directory()])
        p=payload(q.PROVIDER,[provider()])
        with self.assertRaises(ValueError):
            q.screen(d,p,2,1)
        with self.assertRaises(ValueError):
            q.screen(d,p+b"bad\n",1,2)
        with self.assertRaises(ValueError):
            q.screen(d,p.replace(b"Measure Code",b"Other Code",1),1,1)
