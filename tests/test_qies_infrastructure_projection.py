import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text(encoding="utf-8"))
class QiesInfrastructureProjectionTests(unittest.TestCase):
    def test_full_scope_and_prior_distributions(self):
        d=read("research/qies_hospital_infrastructure_audit_20261126.json")
        self.assertEqual(len(d["catalog"]),120)
        self.assertEqual(d["scope_results"]["all"]["rows"],13598)
        self.assertEqual(sum(v["rows"] for k,v in d["scope_results"].items() if k!="all"),13598)
        s=d["scope_results"]["code00_same_state_hospital_candidate"]
        self.assertEqual((s["rows"],len(s["services"]),len(s["counts"])),(5362,57,31))
        self.assertEqual(d["blocked_field"]["field"],"OPRTG_ROOM_CNT")
        for k,v in read("research/public_capability_audit_20261126.json")["qies_field_distributions"].items():
            self.assertEqual(d["scope_results"]["all"]["services"][k],v)
    def test_aggregate_only_projection(self):
        groups={g["id"]:g for s in read("web/public-intelligence.json")["sections"] for g in s["groups"]}
        service=groups["qies-hospital-service-subset"]["rows"]
        count=groups["qies-hospital-count-subset"]["rows"]
        self.assertEqual(len(service),57)
        self.assertEqual(len(count),31)
        self.assertEqual(service[0],["Pharmacy",3754,562,769,123,154])
        for r in service+count:self.assertEqual(sum(r[1:]),5362)
        self.assertNotIn("Operating Room Count",[r[0] for r in count])
        self.assertFalse(any("FTE" in r[0] for r in count))
        self.assertEqual(groups["qies-hospital-comparison"]["rows"][2],["Exact identifier and state candidate pairs",5425])
