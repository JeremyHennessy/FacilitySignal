"""Exercise the real local sidecar recovery path with a tiny synthetic base."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from build_combined import sha
from iqies_additional_services import DDL
from scripts import iqies_service_sidecar as sidecar
from scripts import qualify_iqies_sidecar_roundtrip as q


class RoundtripTests(unittest.TestCase):
    def test_actual_sidecar_and_restore_with_qualified_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "base").mkdir()
            (root / "candidate").mkdir()
            base = root / "base" / "facilitysignal.sqlite3"
            candidate = root / "candidate" / "facilitysignal.sqlite3"
            with closing(sqlite3.connect(base)) as db:
                db.executescript("CREATE TABLE certification_records(registry TEXT,row_number INTEGER,PRIMARY KEY(registry,row_number)); INSERT INTO certification_records VALUES('iqies',1);")
                with closing(sqlite3.connect(candidate)) as dest:
                    db.backup(dest)
                    dest.executescript(DDL)
                    dest.execute("INSERT INTO iqies_additional_service_release VALUES(1,'source','dict','period',1)")
                    dest.execute("INSERT INTO iqies_additional_service_observations VALUES('iqies',1,'ft_srgry_sw','ASC','reported_yes')")
                    dest.commit()
            expected = {
                "base_database_sha256": sha(base), "database_sha256": sha(candidate),
                "base_receipt_sha256": "receipt", "base_release": "fixture",
                "unchanged_base_table_counts": {"certification_records": 1},
                "unchanged_base_tables": 1, "baseline_source_records": 1,
                "service_states": {"reported_yes": 1},
                "field_states": {"ft_srgry_sw": {"reported_yes": 1}},
                "source_sha256": "source", "dictionary_sha256": "dict",
                "source_period": "period", "verified_source_rows": 1,
                "observations": 1, "source_record_filter_checks": 1,
            }
            store = q.ReadOnlyStore(Mock())
            with patch.object(sidecar, "pinned_receipt", return_value=expected), \
                 patch.object(sidecar, "service_checks", return_value={}), \
                 patch.object(q.ext, "national_manifest", return_value={"receipt_sha256": "receipt"}), \
                 patch.object(q.ext, "unchanged") as unchanged, \
                 patch.object(q.national, "run", return_value=expected) as run:
                result = q.qualify(store, root)
                run.assert_called_once_with(store, root)
                unchanged.assert_called_once()
                self.assertTrue(result["extension_tables_exact_bidirectional_parity"])
                self.assertEqual(result["observations"], 1)
                self.assertFalse(result["private_storage_written"])
                self.assertFalse(result["storage_cost_verified"])
                self.assertEqual(sha(base), expected["base_database_sha256"])
                self.assertEqual(result["sidecar_sha256"], sha(root / "service-sidecar" / "services.sqlite3"))
                self.assertEqual(result["restored_database_sha256"], sha(root / "restored.sqlite3"))

    def test_stale_base_rejected_before_reconstruction(self):
        with patch.object(sidecar, "pinned_receipt", return_value={"base_receipt_sha256": "pinned"}), \
             patch.object(q.ext, "national_manifest", return_value={"receipt_sha256": "changed"}), \
             patch.object(q.national, "run") as run:
            with self.assertRaisesRegex(ValueError, "qualified national receipt changed"):
                q.qualify(q.ReadOnlyStore(Mock()), Path("."))
            run.assert_not_called()

    def test_read_only_facade_does_not_expose_write_methods(self):
        underlying = Mock()
        store = q.ReadOnlyStore(underlying)
        for name in ("create", "delete_probe", "container", "service"):
            self.assertFalse(hasattr(store, name))
        store.private()
        store.head("fixture")
        store.chunks("fixture", "etag")
        underlying.private.assert_called_once()
        underlying.head.assert_called_once_with("fixture")
        underlying.chunks.assert_called_once_with("fixture", "etag")
