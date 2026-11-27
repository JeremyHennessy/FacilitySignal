import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from build_combined import sha
from iqies_additional_services import DDL
from scripts import iqies_service_sidecar as s

class SidecarTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.base=self.root/"base.sqlite3"
        self.candidate=self.root/"candidate.sqlite3"
        self.pack=self.root/"pack"
        self.restored=self.root/"restored.sqlite3"
        with closing(sqlite3.connect(self.base)) as db:
            db.executescript("CREATE TABLE certification_records(registry TEXT,row_number INTEGER,PRIMARY KEY(registry,row_number)); INSERT INTO certification_records VALUES('iqies',1);")
            with closing(sqlite3.connect(self.candidate)) as dest:
                db.backup(dest)
                dest.executescript(DDL)
                dest.execute("INSERT INTO iqies_additional_service_release VALUES(1,'source','dict','period',1)")
                dest.execute("INSERT INTO iqies_additional_service_observations VALUES('iqies',1,'ft_srgry_sw','ASC','reported_yes')")
                dest.commit()
        self.receipt={"base_database_sha256":sha(self.base),"database_sha256":sha(self.candidate),"unchanged_base_table_counts":{"certification_records":1},"service_states":{"reported_yes":1},"field_states":{"ft_srgry_sw":{"reported_yes":1}},"source_sha256":"source","dictionary_sha256":"dict","source_period":"period","verified_source_rows":1,"observations":1}
        p=patch.object(s,"pinned_receipt",return_value=self.receipt)
        p.start(); self.addCleanup(p.stop)
        p=patch.object(s,"service_checks",return_value={})
        p.start(); self.addCleanup(p.stop)

    def test_roundtrip(self):
        s.export(self.base,self.candidate,self.pack)
        result=s.restore(self.base,self.pack,self.restored,sha(self.pack/"manifest.json"))
        self.assertTrue(result["base_preserved"])
        self.assertEqual(sha(self.base),self.receipt["base_database_sha256"])
        with closing(sqlite3.connect(self.restored)) as db:
            self.assertEqual(db.execute("SELECT * FROM iqies_additional_service_observations").fetchall(),[("iqies",1,"ft_srgry_sw","ASC","reported_yes")])

    def test_untrusted_manifest(self):
        s.export(self.base,self.candidate,self.pack)
        pin=sha(self.pack/"manifest.json")
        with (self.pack/"manifest.json").open("a") as out: out.write(" ")
        with self.assertRaises(ValueError):
            s.restore(self.base,self.pack,self.restored,pin)
        self.assertFalse(self.restored.exists())

    def test_altered_candidate_rejected(self):
        with closing(sqlite3.connect(self.candidate)) as db:
            db.execute("UPDATE iqies_additional_service_observations SET value_state='reported_no'")
            db.commit()
        with self.assertRaises(ValueError):
            s.export(self.base,self.candidate,self.pack)
        self.assertFalse(self.pack.exists())

    def test_altered_payload_rejected(self):
        s.export(self.base,self.candidate,self.pack)
        pin=sha(self.pack/"manifest.json")
        with closing(sqlite3.connect(self.pack/"services.sqlite3")) as db:
            db.execute("UPDATE iqies_additional_service_observations SET value_state='reported_no'")
            db.commit()
        with self.assertRaises(ValueError):
            s.restore(self.base,self.pack,self.restored,pin)
        self.assertFalse(self.restored.exists())

class ReceiptTests(unittest.TestCase):
    def test_actual_qualification_receipt(self):
        r=s.RECEIPT
        import json
        record=json.loads(r.read_text())
        q=record["receipt"]
        self.assertEqual(record["run"],45974990055)
        self.assertEqual(q["observations"],93913)
        self.assertEqual(sum(q["service_states"].values()),q["observations"])
        self.assertEqual(sum(sum(x.values()) for x in q["field_states"].values()),93913)
        self.assertEqual(len(q["field_states"]),11)
        self.assertEqual(q["unchanged_base_tables"],len(q["unchanged_base_table_counts"]))
        self.assertEqual(q["source_record_filter_checks"],33)
        self.assertTrue(q["national_pointer_unchanged"])
        self.assertFalse(q["private_storage_written"])
        self.assertFalse(q["public_promotion"])
