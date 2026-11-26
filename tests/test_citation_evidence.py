import sqlite3
import unittest
from datetime import date
from citation_evidence import audit,evidence,correction_state,date_state,ROOT

class CitationEvidenceTests(unittest.TestCase):
    def test_no_opportunity_or_risk_inference(self):
        release=date(2026,10,28)
        for status in ("Deficient, Provider has date of correction","Past Non-Compliance","Deficient, Provider has plan of correction","","unmapped source status"):
            e=evidence("nursing-fire","K0123",status,"2026-10-01","2026-09-01",release,True)
            self.assertFalse(e["confirmed_opportunity"])
            self.assertEqual(e["current_regulatory_risk"],"unknown")
        self.assertEqual(correction_state("Deficient, Provider has plan of correction"),"source_reports_plan")
        self.assertEqual(correction_state("not corrected"),"unmapped")
        self.assertEqual(evidence("nursing-fire","E0123","","","2026-01-01",release,True)["source_domain"],"emergency_preparedness_source")
        self.assertEqual(evidence("nursing-health","F0123","","","2026-01-01",release,True)["commercial_relevance"],"context_only")
        self.assertEqual(evidence("nursing-health","K0123","","","2026-01-01",release,False)["evidence_confidence"],"limited")
    def test_dates_do_not_imply_resolution(self):
        release=date(2026,10,28)
        self.assertEqual(date_state("10/11/2026",release),"non_iso_uninterpreted")
        self.assertEqual(date_state("2026-02-30",release),"invalid_iso")
        self.assertEqual(date_state("2026-10-29",release),"after_release")
        self.assertEqual(date_state("",release),"blank")
        e=evidence("nursing-fire","K0123","","2026-10-01","2026-09-01",release,True)
        self.assertEqual(e["review_state"],"status_unknown")
    def test_row_reconciliation_and_no_raw_values(self):
        with sqlite3.connect(":memory:") as db:
            db.executescript((ROOT/"schema.sql").read_text())
            db.execute("INSERT INTO releases VALUES(1,'nursing-fire','2026-10-28','x','x',2,2,0,'x')")
            db.execute("INSERT INTO releases VALUES(2,'nursing','2026-10-28','x','x',1,1,0,'x')")
            db.execute("INSERT INTO current_release VALUES('nursing-fire',1)")
            db.execute("INSERT INTO facilities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("nursing","000001","PRIVATE NAME","private address","city","NY","10000","","","","","","",2))
            rows=[("nursing-fire","a","000001","PRIVATE NAME","NY","2026-01-01","","K0123","","private description","","Deficient, Provider has plan of correction","",1),
                  ("nursing-fire","b","000001","PRIVATE NAME","CA","2026-01-01","","K0123","","private description","","arbitrary private status","",1)]
            db.executemany("INSERT INTO findings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",rows)
            a=audit(db,{"nursing-fire":2})["nursing-fire"]
            self.assertEqual(a["distributions"]["provider_linkage"],{"same_ccn_state_provider_record":1,"unresolved_provider_link":1})
            self.assertEqual(a["distinct_unmapped_correction_values"],1)
            self.assertNotIn("PRIVATE NAME",str(a));self.assertNotIn("arbitrary private status",str(a));self.assertNotIn("000001",str(a))
            with self.assertRaises(ValueError):audit(db,{"nursing-fire":3})
