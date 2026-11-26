"""Reconcile explicit public aggregate projection and reject unexpected types."""
import copy,json,unittest
from pathlib import Path
from scripts.build_public_intelligence import build
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text())
class PublicIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.ledger=read("research/coverage_status.json")
        self.cap=read("research/public_capability_audit_20261126.json")
        self.spec=read("scripts/public_intelligence_spec.json")
    def test_exact_projection(self):
        self.assertEqual(build(self.ledger,self.cap,self.spec),read("web/public-intelligence.json"))
    def test_future_fields_not_exposed(self):
        expected=build(self.ledger,self.cap,self.spec)
        self.ledger["private_future"]={"name":"DO_NOT_PUBLISH"}
        self.ledger["sources"][0]["individual_record"]="DO_NOT_PUBLISH"
        self.assertEqual(expected,build(self.ledger,self.cap,self.spec))
    def test_reconcile_capability_observations(self):
        self.assertEqual(sum(sum(x for x in v.values() if x is not None) for v in self.cap["iqies_field_states"].values()),self.cap["derived_observations"]["iqies"])
        self.assertEqual(sum(sum(x for x in v.values() if x is not None) for v in self.cap["qies_field_distributions"].values()),self.cap["derived_observations"]["qies"])
        self.assertEqual(sum(self.cap["derived_observations"].values()),self.ledger["national_date_normalization_qualified_baseline"]["capability_observations"])
    def test_reconcile_compliance_and_identity(self):
        ce=self.ledger["citation_evidence_qualified_baseline"]
        cd=self.ledger["citation_dictionary_qualified_baseline"]["audit"]
        sc=self.ledger["service_context_qualified_baseline"]["audit"]
        self.assertEqual(sum(ce["source_domains"].values()),ce["citation_rows"])
        for k in ("nursing-fire","nursing-health"):
            self.assertEqual(sum(cd["sources"][k]["lookup_match_counts"].values()),cd["sources"][k]["rows"])
            self.assertEqual(sum(sc["sources"][k]["research_context_counts"].values()),sc["sources"][k]["rows"])
        d=self.ledger["national_date_normalization_qualified_baseline"]
        self.assertEqual(sum(d["date_state_counts"].values()),d["status_observations"])
    def test_reject_unexpected_type(self):
        self.ledger["national_date_normalization_qualified_baseline"]["source_records"]={"private":"value"}
        with self.assertRaises(ValueError):build(self.ledger,self.cap,self.spec)
