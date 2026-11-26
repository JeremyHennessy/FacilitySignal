import sqlite3,tempfile,unittest
from pathlib import Path
from scripts import archive_nppes_organization_keys as p
class NppesKeyPilotTests(unittest.TestCase):
    def test_minimal_schema(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"keys.sqlite3"
            with sqlite3.connect(f) as db:
                db.execute("CREATE TABLE organizations(npi TEXT PRIMARY KEY) WITHOUT ROWID")
                db.execute("INSERT INTO organizations VALUES(?)",("1234567893",))
            self.assertEqual(p.validate_db(f,1)["organization_keys"],1)
            with self.assertRaises(ValueError):p.validate_db(f,2)
            with sqlite3.connect(f) as db:db.execute("ALTER TABLE organizations ADD COLUMN contact TEXT")
            with self.assertRaises(ValueError):p.validate_db(f,1)
    def test_path_scope(self):
        p.safe_name(p.PREFIX+"/"+p.PIN+"/files/organizations.sqlite3")
        for x in (p.archive.POINTER,p.EXT_POINTER,p.PREFIX+"/"+p.PIN+"/files/raw.zip",p.PREFIX+"/"+p.PIN+"/files/../audit.json","TowerSignal/x"):
            with self.assertRaises(ValueError):p.safe_name(x)
