import unittest
from scripts import weekly_azure_refresh as w
class WeeklyRefreshTests(unittest.TestCase):
    def test_release_policy(self):
        old={"release":"2026-10-28","download_url":"https://data.cms.gov/provider-data/a.csv","input_rows":100}
        meta={"released":old["release"],"url":old["download_url"]}
        self.assertEqual(w.release_state(meta,100,old),"unchanged")
        self.assertEqual(w.release_state(meta,101,old),"same_date_revision_review")
        self.assertEqual(w.release_state({**meta,"released":"2026-11-25"},110,old),"new_release")
        self.assertEqual(w.release_state({**meta,"released":"2026-11-25"},10,old),"count_change_review")
        self.assertEqual(w.release_state({**meta,"released":"2026-10-01"},100,old),"older_release_review")
    def test_private_namespace(self):
        self.assertEqual(w.safe_name(w.PREFIX+"/care-compare/hospital/"+"a"*64+"/candidate.sqlite3"),w.PREFIX+"/care-compare/hospital/"+"a"*64+"/candidate.sqlite3")
        for s in (w.archive.POINTER,w.PREFIX+"/care-compare/hospital/"+"a"*64+"/raw.csv","TowerSignal/x",w.PREFIX+"/nppes-weekly/"+"a"*64+"/../complete.json"):
            with self.assertRaises(ValueError):w.safe_name(s)
    def test_weekly_release_discovery(self):
        html='<a href="/nppes/w.zip">NPPES Data Dissemination V.2 - Weekly Update - 111626_112226</a><a href="/nppes/m.zip">NPPES Data Dissemination V.2 (November 09, 2026)</a>'
        weeks,monthly=w.discover_nppes(html)
        self.assertEqual(weeks[0]["end"],"2026-11-22")
        self.assertEqual(monthly["url"],"https://download.cms.gov/nppes/m.zip")
        with self.assertRaises(ValueError):w.discover_nppes(html.replace("/nppes/w.zip","https://example.org/w.zip"))
    def test_fingerprint_is_order_independent(self):
        self.assertEqual(w.fingerprint({"a":1,"b":2}),w.fingerprint({"b":2,"a":1}))
