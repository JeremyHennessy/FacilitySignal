import unittest
from scripts.qualify_hcris_provider_period import evaluate,date_pair
class ProviderPeriodTest(unittest.TestCase):
    def test_ambiguous_dates_never_qualify(self):
        self.assertEqual(date_pair("1/2/2024","2024-01-02"),"unresolved")
        self.assertEqual(date_pair("2024-01-01","2024-01-01"),"equal")
        self.assertEqual(date_pair("2024-01-01","2024-02-01"),"conflict")
    def test_link_and_period_conflicts(self):
        h={"1":("012345","2024-01-01","2024-12-31"),"2":("012345","2024-01-01","2024-12-31"),"3":("012345","2024-05-01","2025-04-30"),"4":("012346","2024-01-01","2024-12-31"),"5":("012347","2024-01-01","2024-12-31"),"6":("012348","2024-01-01","2024-12-31"),"7":("012349","1/2/2024","2024-12-31"),"8":("012350","2024-01-01","2024-12-31")}
        p={k:(v[0],"NY",v[1],v[2]) for k,v in h.items() if k!="8"}
        p["6"]=("012399","NY","2024-01-01","2024-12-31")
        p["9"]=("012351","NY","2024-01-01","2024-12-31")
        d={"012345":{"NY":1},"012346":{"NY":1},"012347":{"NY":2},"012349":{"NY":1}}
        r=evaluate(h,p,d)
        self.assertEqual(r["report_key_intersection"],7)
        self.assertEqual(r["archive_only_report_keys"],1);self.assertEqual(r["puf_only_report_keys"],1)
        self.assertEqual(r["duplicate_period_pairs"],1);self.assertEqual(r["overlapping_distinct_period_pairs"],2)
        self.assertEqual(r["candidate_reports_in_period_conflicts"],3)
        self.assertEqual(r["nonconflicting_candidate_reports"],1)
        self.assertEqual(r["joint_eligibility_states"]["ccn_conflict"],1)
        self.assertEqual(r["joint_eligibility_states"]["unresolved_fiscal_dates"],1)
        self.assertEqual(r["joint_eligibility_states"]["provider_link_ambiguous_directory"],1)
