import sqlite3
import unittest
from scripts import nursing_regulatory_history as m

class NursingRegulatoryHistoryTests(unittest.TestCase):
    def setUp(self):
        self.b=sqlite3.connect(":memory:");self.e=sqlite3.connect(":memory:")
        self.b.executescript("""
        CREATE TABLE facilities(dataset,ccn,state);
        INSERT INTO facilities VALUES('nursing','000001','NY'),('nursing','000002','CA');
        CREATE TABLE current_release(dataset,release_id);
        INSERT INTO current_release VALUES('nursing-health',1),('nursing-fire',2);
        CREATE TABLE findings(dataset,row_hash,ccn,state,survey_date,survey_type,correction_status,correction_date,release_id);
        INSERT INTO findings VALUES('nursing-health','a','000001','NY','2025-01-01','Health Standard','Deficient, Provider has Plan of Correction','',1),
        ('nursing-health','b','000001','NY','2024-01-01','Health Standard','Deficient, Provider has Date of Correction','2024-02-01',1),
        ('nursing-health','c','000001','CA','2025-01-01','Health Standard','','',1),
        ('nursing-health','d','000001','NY','2023-01-01','Health Standard','','',9);
        """)
        self.e.executescript("""
        CREATE TABLE inspection_dates(ordinal,ccn,cycle,processing,kind,date1,date2,health_count,fire_count,link_state);
        CREATE TABLE survey_summary AS SELECT * FROM inspection_dates WHERE 0;
        INSERT INTO inspection_dates VALUES(1,'000001',1,'2026-10-01','Health Standard','2025-01-01',NULL,NULL,NULL,'ccn_present'),
        (2,'000001',1,'2026-10-01','Health Standard','2025-01-01',NULL,NULL,NULL,'ccn_present'),
        (3,'000001',2,'2026-10-01','Fire Safety Standard','2024-02-01',NULL,NULL,NULL,'ccn_present');
        INSERT INTO survey_summary VALUES(1,'000001',1,'2026-10-01','source_summary','2024-01-01','2025-01-01',0,NULL,'same_state');
        CREATE TABLE penalty(row_number,ccn,state,penalty_date,kind,fine_amount,denial_start,denial_days,processing_date,link_state);
        INSERT INTO penalty VALUES(1,'000001','NY','2025-01-01','Fine',1000,NULL,NULL,'2026-10-01','same_state'),
        (2,'000001','NY','2024-01-01','Payment Denial',NULL,'2024-02-01',0,'2026-10-01','same_state'),
        (3,'000001','CA','2025-01-01','Fine',2000,NULL,NULL,'2026-10-01','state_conflict');
        """)
    def tearDown(self):self.b.close();self.e.close()
    def search(self,source,**kw):return m.search(self.b,self.e,source,"000001","NY",**kw)
    def test_citations_preserve_release_and_state(self):
        a=self.search("health_citations",limit=1)
        self.assertEqual(a["source_record_matches"],2)
        self.assertEqual(a["records"][0]["correction_evidence"],"source_reports_plan")
        b=self.search("health_citations",page=2,limit=1)
        self.assertEqual(b["records"][0]["correction_evidence"],"source_reports_date_of_correction")
        self.assertEqual(b["current_enforcement_status"],"unknown")
    def test_duplicate_survey_keys_are_not_merged(self):
        r=self.search("survey_dates",kind="Health Standard",cycle=1,start="2025-01-01",end="2025-01-01")
        self.assertEqual(r["source_record_matches"],2)
        self.assertTrue(all(x["reported_state"] is None and x["link_evidence"]=="ccn_only_directory_candidate" for x in r["records"]))
    def test_summary_explicit_date_and_missing(self):
        with self.assertRaises(ValueError):self.search("survey_summary",start="2025-01-01")
        self.assertEqual(self.search("survey_summary",summary_date="health",start="2025-01-01")["source_record_matches"],0)
        r=self.search("survey_summary",summary_date="fire",start="2025-01-01")["records"][0]
        self.assertEqual(r["reported_health_count"],0);self.assertIsNone(r["reported_fire_count"]);self.assertIsNone(r["reported_state"])
    def test_penalties_not_outstanding_liabilities(self):
        r=self.search("penalties",kind="Payment Denial")
        self.assertEqual(r["source_record_matches"],1)
        self.assertEqual(r["records"][0]["reported_denial_days"],0)
        self.assertIsNone(r["records"][0]["reported_fine_amount_usd"])
        self.assertEqual(r["current_enforcement_status"],"unknown")
    def test_invalid_filters_and_identity(self):
        for kw in ({"kind":"' OR 1=1"},{"cycle":4},{"start":"2025-02-30"},{"limit":101},{"start":"2025-01-02","end":"2025-01-01"}):
            with self.assertRaises(ValueError):self.search("survey_dates",**kw)
        with self.assertRaises(ValueError):m.search(self.b,self.e,"survey_dates","000001","CA")
    def test_profile_keeps_source_grains_separate(self):
        r=m.profile(self.b,self.e,"000001","NY")
        self.assertEqual(set(r["sources"]),set(m.EXPECTED))
        self.assertEqual(r["canonical_merges"],0)
        self.assertNotIn("unique_events",r)
        self.assertEqual(r["current_enforcement_status"],"unknown")
