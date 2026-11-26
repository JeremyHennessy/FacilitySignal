import unittest
from pos_raw_field_profile import FieldProfile, applicability, mapping_codes, scope_for, CAP
from recover_source_headers import recover
class PosRawFieldProfileTests(unittest.TestCase):
    def spec(self, **kwargs):
        return {"semantic_review":"reviewed_provisional_application_mapping","publisher_applicability":"ASC",
                "mapping_reference":None,"interpretation_shape":"count_integer","anomaly":None,**kwargs}
    def test_missing_zero_scope(self):
        p=FieldProfile(self.spec())
        for v in ("","Not Applicable","Not Available","0","3.0","-1","nonsense"):
            p.add(v,"ASC")
        p.add("4","HHA")
        r=p.result(8)
        self.assertEqual(r["states"],{"blank":1,"not_applicable":1,"not_available":1,"other_nonblank":5})
        self.assertEqual(r["scope_counts"]["ASC"]["explicit_zero"],1)
        self.assertEqual(r["scope_counts"]["ASC"]["nonnegative_numeric"],2)
        self.assertEqual(r["scope_counts"]["ASC"]["applicability_conflict"],1)
        self.assertEqual(r["scope_counts"]["HHA"]["out_of_scope_nonblank"],1)
        self.assertEqual(r["numeric_aggregate_by_scope"]["ASC"]["sum"],"3.0")
    def test_mapping_scope(self):
        s=self.spec()
        s.update(publisher_applicability="ASC, HHA",mapping_reference="M5",interpretation_shape="mapped_code")
        maps={"M5":{"entries":[{"code":"1","row":2,"provider_types":"ASC"},
                               {"code":"UA","row":3,"provider_types":"HHA"}]}}
        p=FieldProfile(s,maps)
        for v,scope in [("1","ASC"),("UA","ASC"),("UA","HHA"),("1","HHA")]:p.add(v,scope)
        r=p.result(4)
        self.assertEqual(r["documented_code_counts"],{"ASC":{"1":1},"HHA":{"UA":1}})
        self.assertEqual(r["scope_counts"]["ASC"]["unmatched_code_token"],1)
    def test_unresolved_scope(self):
        s=self.spec();s["publisher_applicability"]="OPT"
        self.assertEqual(applicability(s,"OPT/SLP"),"scope_unresolved")
        s["publisher_applicability"]="ALL EXCEPT FOR PRTF, ICFIID"
        self.assertEqual(applicability(s,"ICFIID"),"out_of_scope")
        self.assertEqual(applicability(s,"ASC"),"applicable")
        self.assertEqual(scope_for("999"),"UNKNOWN_PROVIDER_CODE")
    def test_cardinality_cap_no_raw_output(self):
        p=FieldProfile()
        for i in range(CAP+4):p.add("synthetic_"+str(i))
        r=p.result(CAP+4)
        self.assertEqual(r["distinct_nonmissing"],{"count":CAP+1,"method":"lower_bound"})
        self.assertNotIn("synthetic_",str(r))
    def test_incomplete_headers_rejected(self):
        with self.assertRaises(ValueError):recover({"sources":[]},{"sources":[]},{"sources":[]})
if __name__=="__main__":unittest.main()
