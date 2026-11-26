import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.restore_pinned_archive_samples import validate_projection

class PinnedRestoreTests(unittest.TestCase):
    def test_count_and_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"sample.sqlite3"
            with sqlite3.connect(p) as db:
                db.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY)")
                db.execute("INSERT INTO sample VALUES(1)")
            self.assertEqual(validate_projection(p, {"sample": 1}), {"sample": 1})
            with self.assertRaises(ValueError):
                validate_projection(p, {"sample": 2})
            with self.assertRaises(ValueError):
                validate_projection(p, {"missing": 0})
    def test_readonly_projection_does_not_create_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"absent.sqlite3"
            with self.assertRaises(Exception):
                validate_projection(p, {"sample": 0})
            self.assertFalse(p.exists())
