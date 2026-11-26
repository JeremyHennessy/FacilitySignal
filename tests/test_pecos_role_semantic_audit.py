import unittest
from pecos_role_semantic_audit import role,percentage,date_state,flag,pair,owner_audit,FLAGS_BY
class PecosRoleAuditTests(unittest.TestCase):
    def test_role_scope_and_conflict(self):
        row={"ROLE CODE - OWNER":"85","ROLE TEXT - OWNER":"DIRECT OWNERSHIP INTEREST"}
        self.assertEqual(role(row,"hospital"),("unrecognized","unresolved","unknown_code"))
        self.assertEqual(role(row,"snf"),("85","direct_ownership","matches"))
        row["ROLE TEXT - OWNER"]="INDIRECT OWNERSHIP INTEREST"
        self.assertEqual(role(row,"snf"),("85","unresolved","text_differs"))
    def test_missing_percentage_and_date(self):
        self.assertEqual(percentage("")[0],"blank")
        self.assertEqual(percentage("0")[0],"zero")
        self.assertEqual(percentage("100.01")[0],"outside_0_100")
        self.assertEqual(date_state("11/12/2025")[0],"ambiguous_slash")
        self.assertEqual(date_state("2026-12-01")[0],"parsed_future")
        self.assertEqual(flag(""),"blank")
        self.assertEqual(flag("N"),"no")
    def test_strict_keys(self):
        self.assertIsNone(pair({"ENROLLMENT ID":"X"*15,"ASSOCIATE ID":"123"}))
        self.assertEqual(pair({"ENROLLMENT ID":"X"*15,"ASSOCIATE ID":"0"*9+"1"}),("X"*15,"0"*9+"1"))
    def test_skip_individual_before_access_and_flag_conflict(self):
        r={"TYPE - OWNER":"O","ROLE CODE - OWNER":"43","ROLE TEXT - OWNER":"OPERATIONAL/MANAGERIAL CONTROL",
          "PERCENTAGE OWNERSHIP":"","ASSOCIATION DATE - OWNER":"2025-01-01","ASSOCIATE ID - OWNER":"1"*10,
          "ENROLLMENT ID":"X"*15,"ASSOCIATE ID":"2"*10}
        r.update({f+" - OWNER":"N" for f in FLAGS_BY["hospital"]})
        t=dict(r);t["REIT - OWNER"]="Y"
        _,a=owner_audit([{"TYPE - OWNER":"I"},r,t],"hospital",{("X"*15,"2"*10):[("","","")]})
        self.assertEqual(a["input_owner_type_counts"],{"I":1,"O":2})
        self.assertEqual(a["counts"]["exact_enrollment_pac_candidate"],2)
        self.assertEqual(a["flags"]["REIT"]["valid_pacs_with_both_yes_no"],1)
        self.assertEqual(a["distinct_valid_org_enrollment_provider_pairs"],1)
if __name__=="__main__":unittest.main()
