import csv,io,sqlite3,tempfile,unittest
from pathlib import Path
from scripts import archive_state_equipment_directory as m
class StateEquipmentDirectoryTests(unittest.TestCase):
    def test_minnesota_aggregate_preserves_duplicate_count_only(self):
        scope=m.SCOPES["mn-elevator"];f=io.StringIO(newline="");w=csv.DictWriter(f,fieldnames=scope["headers"]);w.writeheader()
        w.writerow({"Asset_Number":"private_id","BusinessName":"private_name","ExpirationDate":"11/26/2026"})
        w.writerow({"Asset_Number":"private_id","ExpirationDate":"unresolved"})
        f.seek(0);s=m.mn_project(f,scope)
        self.assertEqual(s["source_rows_screened"],2);self.assertEqual(s["asset_number_states"],{"distinct_asset_number":1,"repeated_asset_number":1})
        self.assertEqual(s["date_value_states"]["ExpirationDate"],{"valid_calendar_date":1,"date_review":1})
        self.assertNotIn("private_id",str(s));self.assertNotIn("private_name",str(s))
    def test_illinois_literal_rows_and_no_contacts(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"db.sqlite3";s=m.il_project([{"facility_name":"Hospital","license_number":"001-A","phone":"private phone","address":"private street","exp_date":"2026-12-31T00:00:00.000"},{"facility_name":"Hospital","license_number":"001-A"}],p)
            self.assertEqual(s["stored_rows"],2);self.assertEqual(s["license_and_expiry_states"]["repeated_license"],1)
            with sqlite3.connect(p) as db:self.assertEqual(db.execute("SELECT license_number FROM institutional_directory ORDER BY source_ordinal").fetchall(),[("001-A",),("001-A",)])
            self.assertNotIn(b"private phone",p.read_bytes());self.assertNotIn(b"private street",p.read_bytes())
    def test_unreviewed_header_rejected(self):
        with self.assertRaises(ValueError):m.mn_project(io.StringIO("wrong_header\n1\n"),m.SCOPES["mn-boiler"])
