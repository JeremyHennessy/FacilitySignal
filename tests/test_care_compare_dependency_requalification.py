import copy,unittest,json
from scripts import requalify_care_compare_dependencies as m
class DependencyTests(unittest.TestCase):
    def fixture(self,key):
        row={"ccn":"000001","name":"Test","address":"A","city":"City","state":"NY","zip":"00000","capacity":""}
        pin={"key":key,"release":"2026-11-01","sha256":"a"*64,"stored_rows":1,"input_rows":1}
        shard={"source":key,"release":pin["release"],"row_count":1,"records":[row]}
        ident={k:row[k] for k in m.FIELDS}
        return shard,pin,ident
    def test_hha_exact_indicators_and_new_value_gate(self):
        shard,pin,ident=self.fixture(m.q.HHA)
        raw={"Offers "+k+" Services":"Yes" for k in m.q.SERVICES};raw["Offers Nursing Care Services"]="-"
        data,e=m.hha_projection(shard,pin,{("000001","NY"):(raw,ident)},"b"*64)
        self.assertEqual(json.loads(data)["records"]["NY:000001"]["Nursing Care"],"dash_marker")
        self.assertEqual(e["field_states"]["Nursing Care"],{"dash_marker":1})
        raw["Offers Nursing Care Services"]="new unknown"
        with self.assertRaises(ValueError):m.hha_projection(shard,pin,{("000001","NY"):(raw,ident)},"b"*64)
    def test_ltch_capacity_domain_and_identity_gate(self):
        shard,pin,ident=self.fixture(m.q.LTCH)
        raw={"Total Number of Beds":"0017"}
        data,e=m.ltch_projection(shard,pin,{("000001","NY"):(raw,ident)})
        self.assertEqual(json.loads(data)["records"][0]["capacity"],"17");self.assertEqual(e["sum"],17)
        self.assertEqual(shard["records"][0]["capacity"],"")
        raw["Total Number of Beds"]="not a reported count"
        with self.assertRaises(ValueError):m.ltch_projection(shard,pin,{("000001","NY"):(raw,ident)})
        raw["Total Number of Beds"]="17";bad={**ident,"name":"Different"}
        with self.assertRaises(ValueError):m.ltch_projection(shard,pin,{("000001","NY"):(raw,bad)})
