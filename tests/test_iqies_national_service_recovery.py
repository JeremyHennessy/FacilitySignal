import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from scripts.qualify_iqies_national_services import preservation
from iqies_additional_services import DDL

class NationalServicePreservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)/"base.sqlite3"
        self.candidate=Path(self.tmp.name)/"candidate.sqlite3"
        with closing(sqlite3.connect(self.base)) as db:
            db.executescript("""
                CREATE TABLE certification_records(registry TEXT,row_number INTEGER,PRIMARY KEY(registry,row_number));
                INSERT INTO certification_records VALUES('iqies',1);
                CREATE TABLE samples(value TEXT);
                INSERT INTO samples VALUES('a'),('a'),('b');
                CREATE INDEX sample_value ON samples(value);
                CREATE VIEW sample_view AS SELECT value FROM samples;
            """)
            with closing(sqlite3.connect(self.candidate)) as dest:
                db.backup(dest)
                dest.executescript(DDL)
                dest.commit()

    def edit(self, sql):
        with closing(sqlite3.connect(self.candidate)) as db:
            db.executescript(sql)
            db.commit()

    def test_exact_preservation(self):
        self.assertEqual(preservation(self.base,self.candidate),{"certification_records":1,"samples":3})

    def test_duplicate_multiplicity_rejected(self):
        self.edit("DELETE FROM samples WHERE rowid=1; INSERT INTO samples VALUES('b');")
        with self.assertRaises(ValueError):
            preservation(self.base,self.candidate)

    def test_index_drift_rejected(self):
        self.edit("DROP INDEX sample_value;")
        with self.assertRaises(ValueError):
            preservation(self.base,self.candidate)

    def test_unexpected_table_rejected(self):
        self.edit("CREATE TABLE unexpected(value TEXT);")
        with self.assertRaises(ValueError):
            preservation(self.base,self.candidate)
