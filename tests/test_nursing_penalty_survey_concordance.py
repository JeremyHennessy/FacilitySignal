"""Synthetic checks independent of any private archive access."""
import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from scripts.nursing_penalty_survey_concordance import concordance, day, profile

class ConcordanceTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE penalty(ccn,link_state,penalty_date,kind);
            CREATE TABLE inspection_dates(ccn,link_state,date1);
            CREATE TABLE survey_summary(ccn,link_state,date1,date2);
        """)

    def test_field_and_same_day_grains(self):
        self.db.executemany("INSERT INTO inspection_dates VALUES(?,?,?)",[
            ("AAAAAA","ccn_present","2026-04-04"),("AAAAAA","ccn_present","2026-04-04"),
            ("AAAAAA","unmatched_ccn","2026-06-06"),("OTHERX","ccn_present","2026-06-06"),
            ("AAAAAA","ccn_present","2026-01-01"),
        ])
        self.db.executemany("INSERT INTO survey_summary VALUES(?,?,?,?)",[
            ("AAAAAA","same_state","2026-02-02","2026-04-04"),
            ("AAAAAA","state_conflict","2026-06-06","2026-06-06"),
        ])
        self.db.executemany("INSERT INTO penalty VALUES(?,?,?,?)",[
            ("AAAAAA","same_state",d,"Fine") for d in ("2026-04-04","2026-02-02","2026-06-06","2026-01-01")
        ])
        r=concordance(self.db)
        counts=r["penalty_source_rows_by_kind_and_date_concordance"]["Fine"]
        self.assertEqual([counts[x] for x in ("both_survey_sources","only_prior_same_state_summary",
                                            "neither_survey_source","only_ccn_only_inspection_dates")],[1,1,1,1])
        self.assertEqual(r["survey_field_coverage"]["inspection_dates"]["distinct_directory_candidate_ccn_dates"],3)
        self.assertEqual(r["canonical_event_links"],0)
        for identifier in ("AAAAAA","OTHERX","2026-06-06"):
            self.assertNotIn(identifier,json.dumps(r))

    def test_date_and_linkage_abstentions(self):
        self.db.executemany("INSERT INTO penalty VALUES(?,?,?,?)",[
            ("AAAAAA","same_state",None,"Payment Denial"),
            ("AAAAAA","same_state","2026-02-30","Payment Denial"),
            ("AAAAAA","same_state","2026-10-29","Payment Denial"),
            ("AAAAAA","state_conflict","2026-04-04","Payment Denial"),
        ])
        counts=concordance(self.db)["penalty_source_rows_by_kind_and_date_concordance"]["Payment Denial"]
        self.assertEqual([counts[x] for x in ("missing_penalty_date","invalid_penalty_date",
                                            "penalty_date_after_release","unresolved_directory")],[1,1,1,1])
        self.assertEqual(day("2026-10-28"),("in_window","2026-10-28"))

    def test_wrong_database_rejected(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/"not-the-archive.sqlite3"
            with sqlite3.connect(p) as db:
                db.execute("CREATE TABLE sample(value)")
            with self.assertRaisesRegex(ValueError,"exact regular local"):
                profile(p)

if __name__=="__main__":
    unittest.main()
