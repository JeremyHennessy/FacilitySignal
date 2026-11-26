import sqlite3
import unittest
from citation_evidence import ROOT
from service_context import context, audit

class ServiceContextTests(unittest.TestCase):
    def test_exact_category_and_domain_gate(self):
        self.assertEqual(context("nursing-health","F0880"," Infection Control Deficiencies "), "infection_prevention_context")
        self.assertEqual(context("nursing-health","F0812","Nutrition and Dietary Deficiencies"), "food_service_context")
        self.assertEqual(context("nursing-health","F0880","unreviewed infection wording"), "other_health_context")
        self.assertEqual(context("nursing-health","K0880","Infection Control Deficiencies"), "unresolved_domain")
        self.assertEqual(context("nursing-fire","K0123","Infection Control Deficiencies"), "broad_life_safety_context")
        self.assertEqual(context("nursing-fire","E0123",""), "broad_preparedness_context")
    def test_reconcile_and_no_row_data(self):
        with sqlite3.connect(":memory:") as db:
            db.executescript((ROOT/"schema.sql").read_text())
            db.execute("INSERT INTO releases VALUES(1,'nursing-health','2026-10-28','x','x',2,2,0,'x')")
            db.execute("INSERT INTO current_release VALUES('nursing-health',1)")
            rows=[("nursing-health","a","000001","PRIVATE NAME","NY","2026-01-01","","F0880","Infection Control Deficiencies","private description","","Deficient, Provider has plan of correction","",1),
                  ("nursing-health","b","000002","PRIVATE NAME","CA","2026-01-01","","F0812","private category","private description","","private status","2026-11-01",1)]
            db.executemany("INSERT INTO findings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",rows)
            out=audit(db,{"nursing-health":2})["nursing-health"]
            self.assertEqual(out["research_context_counts"],{"infection_prevention_context":1,"other_health_context":1})
            self.assertEqual(out["date_state_counts"],{"on_or_before_release/blank":1,"on_or_before_release/after_release":1})
            for value in ("PRIVATE NAME","000001","private category","private status","private description","2026-11-01"):
                self.assertNotIn(value,str(out))
            with self.assertRaises(ValueError):
                audit(db,{"nursing-health":3})
