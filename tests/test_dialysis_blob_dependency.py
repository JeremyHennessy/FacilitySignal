import copy,unittest
from scripts import requalify_dialysis_blob_dependency as m
class DialysisBlobDependencyTests(unittest.TestCase):
    def fixture(self):
        row={"ccn":"000001","name":"Test","address":"A","city":"City","state":"NY","zip":"00000","capacity":"8"}
        shard={"source":"dialysis","release":"2026-11-01","row_count":1,"records":[row]}
        pin={"release":"2026-11-01","stored_rows":1}
        identity={"prvdr_num":"000001","state_cd":"NY","st_adr":" a ","city_name":"city","zip_cd":"00000-1234"}
        values={k:({"state":"reported_count","count":12} if m.RULES[k][1]=="count" else {"state":"reported_yes"}) for k in m.FIELDS}
        return shard,pin,identity,values
    def test_exact_corroboration_and_new_care_compare_source(self):
        shard,pin,identity,values=self.fixture()
        records,stats=m.project(shard,pin,[(identity,values)])
        self.assertEqual(records,{"000001":values});self.assertEqual(stats["published_candidate_rows"],1)
        self.assertNotIn("prvdr_num",str(records))
        with self.assertRaises(ValueError):m.project(shard,pin,[(identity,values),(identity,values)])
        wrong={**identity,"st_adr":"other address"}
        with self.assertRaises(ValueError):m.project(shard,pin,[(wrong,values)])
    def test_unreviewed_registry_version_does_not_generate_pack(self):
        report={"sources":{"registry_and_ownership":{"iqies":{"state":"new_version_review"}}}}
        result=m.qualify(None,None,{"dialysis"},None,None,report)
        self.assertEqual(result["status"],"REGISTRY_REVIEW_REQUIRED")
        self.assertFalse(result["public_promotion"])
