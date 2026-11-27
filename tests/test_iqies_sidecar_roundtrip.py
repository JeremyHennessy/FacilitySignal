"""Exercise the real local sidecar recovery path with a tiny synthetic base."""
import io
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, call, patch

import private_iqies_service_research as service
from build_combined import sha
from iqies_additional_services import DDL
from scripts import iqies_service_sidecar as sidecar
from scripts import qualify_iqies_sidecar_roundtrip as q
from test_azure_private_workspace import fixture


class RoundtripTests(unittest.TestCase):
    def test_cli_smokes_actual_app_on_same_pinned_restore(self):
        for drift in (None, "digest", "row lineage"):
            with self.subTest(drift=drift), fixture() as base, tempfile.TemporaryDirectory() as directory:
                outside = Path(directory)
                candidate = outside / "candidate.sqlite3"
                with closing(sqlite3.connect(base)) as db, closing(sqlite3.connect(candidate)) as dest:
                    db.backup(dest)
                    dest.execute("PRAGMA foreign_keys=ON")
                    dest.executescript("BEGIN IMMEDIATE;\n" + DDL)
                    dest.execute("INSERT INTO iqies_additional_service_release VALUES(1,?,?,?,1)",
                                 ("a"*64, service.DICT_SHA, "2026-Q3"))
                    dest.execute("INSERT INTO iqies_additional_service_observations "
                                 "VALUES('iqies',1,'ft_srgry_sw','ASC','not_available')")
                    dest.commit()
                table_counts = q.national.preservation(base, candidate)
                expected = {
                    "base_database_sha256": sha(base), "database_sha256": sha(candidate),
                    "base_receipt_sha256": "receipt", "base_release": "bootstrap-123-1",
                    "unchanged_base_table_counts": table_counts,
                    "unchanged_base_tables": len(table_counts), "baseline_source_records": 2,
                    "service_states": {"not_available": 1},
                    "field_states": {"ft_srgry_sw": {"not_available": 1}},
                    "source_sha256": "a"*64, "dictionary_sha256": service.DICT_SHA,
                    "source_period": "2026-Q3", "verified_source_rows": 1,
                    "observations": 1, "source_record_filter_checks": 1,
                }
                verified = outside / "national.json"
                workspace_pin = outside / "roundtrip.json"
                receipt = outside / "receipt.json"
                app_source = {**expected, "source_period": "wrong"} if drift == "row lineage" else expected
                verified.write_text(json.dumps({"receipt": app_source}))
                workspace_pin.write_text(json.dumps({"receipt": {
                    **expected,
                    "restored_database_sha256": "0"*64 if drift == "digest" else expected["database_sha256"],
                    "extension_tables_exact_bidirectional_parity": True,
                    "national_pointer_unchanged": True,
                }}))
                manifest = {"receipt_sha256": "receipt",
                            "pointer": {"release": expected["base_release"]},
                            "receipt": {"database_sha256": expected["base_database_sha256"]}}

                def local_reconstruction(store, root):
                    self.assertIsInstance(store, q.ReadOnlyStore)
                    for name, source in (("base", base), ("candidate", candidate)):
                        (root / name).mkdir()
                        shutil.copyfile(source, root / name / "facilitysignal.sqlite3")
                    return expected

                output = io.StringIO()
                store = Mock()
                with patch.object(sidecar, "pinned_receipt", return_value=expected), \
                     patch.object(sidecar, "service_checks", return_value={}), \
                     patch.object(service, "NATIONAL", verified), \
                     patch.object(service, "ROUNDTRIP", workspace_pin), \
                     patch.object(q.ext, "national_manifest", return_value=manifest), \
                     patch.object(q.ext, "unchanged") as unchanged, \
                     patch.object(q.national, "run", side_effect=local_reconstruction) as run, \
                     patch.object(q.archive, "Azure", return_value=store), \
                     patch.object(q.archive, "run_key"), \
                     patch.object(q, "verify_workspace", wraps=q.verify_workspace) as smoke, \
                     patch.object(sys, "argv", ["roundtrip", "--receipt", str(receipt)]), \
                     redirect_stdout(output):
                    if drift:
                        error = ("unqualified extension recovery" if drift == "digest"
                                 else "extension count differs")
                        with self.assertRaisesRegex(ValueError, error):
                            q.main()
                        self.assertFalse(receipt.exists())
                        self.assertEqual(output.getvalue(), "")
                        unchanged.assert_not_called()
                    else:
                        q.main()
                        result = json.loads(receipt.read_text())
                        self.assertTrue(result["extension_tables_exact_bidirectional_parity"])
                        self.assertEqual(result["observations"], 1)
                        self.assertFalse(result["private_storage_written"])
                        self.assertFalse(result["storage_cost_verified"])
                        self.assertEqual(result["restored_database_sha256"], sha(candidate))
                        self.assertEqual(result["workspace_smoke"], {
                            "source": "private_azure_archive", "release": "bootstrap-123-1",
                            "source_records": 2, "read_only": True,
                            "qualified_service_extension_observations": 1,
                            "extension_route_verified": True, "filtered_provider_records": 1,
                            "service_observations": 1, "provider_profile_verified": True,
                            "snapshot_unchanged": True, "http_smoke": "PASS",
                        })
                        for private in ("Fixture Hospital", "Fixture ASC", "000001", "000002"):
                            self.assertNotIn(private, receipt.read_text())
                            self.assertNotIn(private, output.getvalue())
                        unchanged.assert_called_once_with(run.call_args.args[0], manifest)
                    run.assert_called_once()
                    smoke.assert_called_once()
                    self.assertEqual(smoke.call_args.args[0], run.call_args.args[1] / "restored.sqlite3")
                    self.assertFalse(run.call_args.args[1].exists())
                    self.assertEqual(sha(base), expected["base_database_sha256"])
                    self.assertEqual(store.mock_calls, [call.close()])

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
