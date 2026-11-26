import json
import sqlite3
import unittest
from scripts import institutional_search as q
import institutional_observations as inst

class InstitutionalSearchTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        inst.setup(self.db)
        pin={"release":"2026-10-28","sha256":"a"*64}
        raw_header=[r[0] for r in inst.RULES["dialysis"].values()]
        data={}
        for ccn,state,values in [
            ("000001","NY",["Yes","No","Yes","No","Yes"]),
            ("000002","NY",["Yes","Yes","Yes","Yes","No"]),
            ("000003","CA",["No","Yes","Yes","Yes","Yes"]),
            ("000004","CA",["No","No","No","No","No"])]:
            data[(ccn,state)]=(dict(zip(raw_header,values)),{"ccn":ccn,"state":state})
        inst.add_source(self.db,"dialysis",pin,data,"b"*64)
    def tearDown(self):
        self.db.close()
    def test_exact_filters_and_pagination(self):
        a=q.search(self.db,"dialysis",{"late_shift":"reported_yes","peritoneal_dialysis":"reported_yes"},"NY")
        self.assertEqual(a["total"],1)
        self.assertEqual(a["records"],[{"source":"dialysis","ccn":"000002","state":"NY"}])
        self.assertEqual(q.search(self.db,"dialysis",{},page=2,limit=1)["records"][0]["ccn"],"000004")
        self.assertEqual(q.search(self.db,"dialysis",{},page=5,limit=1)["records"],[])
    def test_exact_profile_and_missing_not_negative(self):
        self.assertIsNone(q.profile(self.db,"dialysis","000001","CA"))
        row=q.profile(self.db,"dialysis","000001","NY")
        self.assertEqual(row["observations"]["late_shift"],"reported_no")
        self.assertEqual(row["release"],"2026-10-28")
    def test_invalid_field_value_state_and_injection(self):
        for filters in ({"sprinklers":"partial"},{"late_shift":"not_available"},{"late_shift":"' OR 1=1"}):
            with self.assertRaises(ValueError):q.search(self.db,"dialysis",filters)
        with self.assertRaises(ValueError):q.search(self.db,"dialysis",{},"ZZ")
        with self.assertRaises(ValueError):q.search(self.db,"dialysis",{},limit=101)
        with self.assertRaises(ValueError):q.profile(self.db,"dialysis","000001",None)
    def test_policy_partition_and_prior_count(self):
        prior=json.loads(q.QUAL.read_text())
        self.assertEqual(sum(len(x) for x in q.PUBLIC_CANDIDATE.values()),7)
        self.assertEqual(sum(len(x) for x in q.PRIVATE_ONLY.values()),3)
        public=sum(prior["sources"][s]["providers"]*len(fs) for s,fs in q.PUBLIC_CANDIDATE.items())
        self.assertEqual(public,57476)
        self.assertEqual(prior["observations"]-public,44058)
        self.assertNotIn("sprinklers",q.PUBLIC_CANDIDATE["nursing"])
