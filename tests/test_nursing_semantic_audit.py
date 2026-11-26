import unittest
from nursing_semantic_audit import yn,version,citation,chain_audit,FLAGS
class NursingSemanticTests(unittest.TestCase):
    def test_dispute_unknown_not_no(self):
        self.assertEqual([yn(v) for v in ("Y","N","","Yes")],["yes","no","blank","unrecognized"])
        self.assertEqual(version("New"),"new")
    def test_joint_and_tag_version(self):
        r={f:"N" for f in FLAGS}
        r.update({"Citation under IDR":"Y","Citation under IIDR":"Y","Inspection Cycle":"1","Tag Version":"New","Survey Date":"2020-01-01"})
        result=citation([r],True)
        self.assertEqual(result["idr_iidr_joint_counts"],{"yes/yes":1})
        self.assertEqual(result["tag_version_date_agreement"],{"agrees":1})
    def test_affiliation_conflict_no_merge(self):
        n={"CMS Certification Number (CCN)":"001001","Chain ID":"12","Chain Name":"Example","Number of Facilities in Chain":"1","State":"NY"}
        p={"CCN":"001001","STATE":"NY","AFFILIATION ENTITY ID":"13","AFFILIATION ENTITY NAME":"Example"}
        result=chain_audit([n],[p])
        self.assertEqual(result["cross_source_exact_ccn_state"]["both_populated_different"],1)
        self.assertEqual(result["chains"]["reported_size_matches_observed_members"],1)
        self.assertNotIn("Example",str(result))
if __name__=="__main__":unittest.main()
