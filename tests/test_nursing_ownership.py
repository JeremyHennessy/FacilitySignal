import csv
import io
import sqlite3
import unittest
from contextlib import closing
from scripts.qualify_nursing_ownership import HEADER, project, percentage, date_value

def row(kind="Organization", role="DIRECT OWNERSHIP INTEREST", name="Example Institution LLC"):
    return ["012345", "Example Facility", "excluded address", "Town", "NY", "10001", role, kind, name, "50", "2020-01-01", "excluded location", "2026-11-01"]

def stream(rows, header=HEADER):
    s = io.StringIO(newline="")
    w = csv.writer(s)
    w.writerow(header)
    w.writerows(rows)
    s.seek(0)
    return s

class NursingOwnershipTest(unittest.TestCase):
    def test_scope_and_reconciliation(self):
        rows = [row(), row(), row("Individual", name="Never retain"), row("Unknown"), row(role="unreviewed")]
        with closing(sqlite3.connect(":memory:")) as db:
            result = project(stream(rows), len(rows), db)
            self.assertEqual(result["stored_organization_rows"], 2)
            self.assertEqual(result["repeated_projected_tuple_rows"], 1)
            self.assertEqual(result["dispositions"]["excluded_individual"], 1)
            self.assertEqual(result["dispositions"]["excluded_unknown_owner_type"], 1)
            self.assertEqual(result["dispositions"]["excluded_role_review"], 1)
            self.assertEqual(db.execute("SELECT DISTINCT owner_name FROM organization_role").fetchall(), [("Example Institution LLC",)])
            cols = [r[1] for r in db.execute("PRAGMA table_info(organization_role)")]
            self.assertNotIn("Provider Address", cols)
    def test_header_and_count_fail_closed(self):
        for s,n in ((stream([row()], HEADER[:-1]), 1), (stream([row()]), 2)):
            with closing(sqlite3.connect(":memory:")) as db:
                with self.assertRaises(ValueError):
                    project(s, n, db)
    def test_missing_values(self):
        self.assertEqual(percentage(""), (None, "blank"))
        self.assertEqual(percentage("101"), (None, "range_review"))
        self.assertEqual(percentage("50%"), (None, "value_review"))
        self.assertEqual(date_value("2026-02-30"), (None, "date_review"))
        self.assertEqual(date_value("01/02/2026"), (None, "date_review"))

if __name__ == "__main__":
    unittest.main()
