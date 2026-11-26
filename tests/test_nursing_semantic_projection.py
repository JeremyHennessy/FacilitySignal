import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads((ROOT/path).read_text())
class NursingSemanticProjectionTests(unittest.TestCase):
    def test_source_reconciliation(self):
        a=read("research/nursing_semantic_audit_20261126.json")
        self.assertEqual(a["qualification_run"],45826186143)
        r={x["group"]:x["result"] for x in a["audits"]}
        c=r["chains"];self.assertEqual(c["nursing"]["rows"],14686)
        self.assertEqual(c["chains"]["groups"],c["chains"]["reported_size_matches_observed_members"])
        self.assertEqual(sum(c["chains"]["observed_membership_size_bands"].values()),612)
        p=c["cross_source_exact_ccn_state"]
        self.assertEqual(sum(v for k,v in p.items() if k!="same_ccn_state_pairs"),14207)
        for s in r["citations"].values():
            for v in s["flags"].values():self.assertEqual(sum(v.values()),s["rows"])
            self.assertEqual(sum(s["idr_iidr_joint_counts"].values()),s["rows"])
    def test_public_projection_only_approved_aggregates(self):
        s=read("web/public-intelligence.json")
        groups={g["id"]:g for sec in s["sections"] for g in sec["groups"]}
        self.assertEqual(groups["nursing-inspection-disputes"]["rows"][-2:],
            [["Informal dispute resolution (IDR)",631,69],["Independent informal dispute resolution (IIDR)",131,1]])
        self.assertEqual(groups["nursing-chain-coverage"]["rows"][3],["Reported chain groups",612])
        self.assertEqual(groups["nursing-affiliation-corroboration"]["rows"][1],["Equal populated group IDs",9981])
