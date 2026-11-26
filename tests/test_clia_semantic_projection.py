"""Verify the qualified CLIA semantic projection and its restricted scope."""
import copy,json,unittest
from pathlib import Path
from scripts.build_public_intelligence import qualify_clia_semantic,build
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text())
class CliaSemanticProjectionTests(unittest.TestCase):
    def setUp(self):
        self.audit=read("research/clia_certificate_semantic_audit_20261126.json")
        self.prior=read("research/clia_domain_link_audit_20261126.json")
        self.pin=read("research/snapshot_release_20261125.json")
    def test_exact_scopes_and_boundaries(self):
        x=qualify_clia_semantic(self.audit,self.prior,self.pin)
        self.assertEqual(x["scopes"],{"literal_00":299345,"other_documented":386615,"unresolved":98})
        self.assertEqual(x["certificates"]["literal_00"]["code_2"],244230)
        self.assertEqual(x["facility_00"]["code_21"],115548)
        self.assertEqual(x["accreditation"]["CAP"],{"reported":8507,"confirmed":8012,"unconfirmed":495,"code00_confirmed":7058})
        self.assertEqual(x["unmatched_references"],403)
        self.assertEqual(x["reversed_dates"],1)
        self.assertEqual(x["dates"]["literal_00/TRMNTN_EXPRTN_DT"],{"before":1180,"after":298165,"other":0})
    def test_reject_unqualified_scope(self):
        x=copy.deepcopy(self.audit);x["clia_term_scope_rows"]["literal_00"]+=1
        with self.assertRaises(ValueError):qualify_clia_semantic(x,self.prior,self.pin)
    def test_reject_unqualified_source(self):
        x=copy.deepcopy(self.audit);x["source_sha256"]="unknown"
        with self.assertRaises(ValueError):qualify_clia_semantic(x,self.prior,self.pin)
    def test_no_record_projection(self):
        x=build(read("research/coverage_status.json"),read("research/public_capability_audit_20261126.json"),read("scripts/public_intelligence_spec.json"))
        groups=[g for s in x["sections"] for g in s["groups"] if g["id"].startswith("clia-semantic-")]
        self.assertEqual(len(groups),6)
        self.assertTrue(all(g["run"]==45831429985 for g in groups))
        self.assertEqual(len(next(g for g in groups if g["id"]=="clia-semantic-facility-type")["rows"]),29)
        self.assertTrue(all(type(c) in (str,int) for g in groups for r in g["rows"] for c in r))
