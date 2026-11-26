import unittest
from decimal import Decimal
from qies_infrastructure_audit import service,number,flag,identity,Quantity,compare_totals,COUNTS
class QiesInfrastructureAuditTests(unittest.TestCase):
    def test_preserve_states(self):
        self.assertEqual([service(x) for x in ("0","1","","Not Available","4")],["code_0","code_1","blank","not_available","unrecognized"])
        self.assertEqual(flag("N"),"literal_N")
        self.assertEqual(number("0"),("zero",Decimal(0)))
        self.assertEqual(number("1.5"),("noninteger",None))
        self.assertEqual(number("1.5",True),("positive",Decimal("1.5")))
    def test_numeric_diagnostics(self):
        p=Quantity()
        for v in ("0","7","2.0","","-1"):p.add(v)
        self.assertEqual(p.result(5)["numeric_sum_diagnostic_only"],"9.0")
        self.assertEqual(p.result(5)["states"],{"zero":1,"positive":2,"blank":1,"negative":1})
    def test_identity_scope(self):
        r={"PRVDR_NUM":"012345","STATE_CD":"NY"}
        self.assertEqual(identity(r,{"012345":[{"state":"NJ"}]})[0],"id_candidate_state_conflict_or_missing")
        self.assertEqual(identity(r,{"012345":[{"state":"NY"}]})[0],"same_state_candidate")
        r["PRVDR_NUM"]="12345"
        self.assertEqual(identity(r,{})[0],"non_six_character_id")
    def test_component_diagnostic(self):
        self.assertEqual(len(COUNTS),31)
        self.assertEqual(compare_totals({"a":2,"b":3,"t":4},"t",("a","b")),"component_sum_above_reported_total")
        self.assertEqual(compare_totals({"a":None,"b":3,"t":4},"t",("a","b")),"not_comparable")
