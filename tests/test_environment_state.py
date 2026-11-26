import tempfile,sqlite3,unittest
from pathlib import Path
from scripts import archive_environment_state as m
class StateArchiveTests(unittest.TestCase):
    def test_pagination_scope(self):
        d={"data":[{"entity_id":1}],"meta":{"current_page":1,"last_page":1,"total":1}}
        self.assertEqual(m.page_rows(d,1),([{"entity_id":1}],1,1))
        with self.assertRaises(Exception):m.page_rows(d,2)
    def test_aggregate_no_source_rows(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"aggregate.db";m.write_aggregate(p,{"source_rows_screened":100,"site_or_system_rows_retained":0})
            with sqlite3.connect(p) as db:self.assertEqual(db.execute("SELECT count(*) FROM aggregate_evidence").fetchone()[0],1)
    def test_source_host_boundary(self):
        self.assertEqual(m.allowed(m.IL+"/api/hospitals"),m.IL+"/api/hospitals")
        with self.assertRaises(Exception):m.allowed("https://example.com/api/hospitals")
