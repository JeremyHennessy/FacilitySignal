from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

import facilitysignal
from build_combined import sha
from scripts.azure_private_workspace import restored_snapshot, verify_workspace, workspace_handler


@contextmanager
def fixture():
    with TemporaryDirectory() as work:
        path = Path(work)
        db = path / "source.sqlite3"
        facilitysignal.init(db)
        csv = path / "hospital.csv"
        csv.write_text("CMS Certification Number (CCN),Facility Name,Address,City,State,ZIP Code\n"
                       "000001,Fixture Hospital,1 Example Street,Test City,NY,10001\n")
        facilitysignal.import_csv(db, "hospital", csv, "2026-11-01", 1)
        yield db


class PrivateWorkspaceTest(unittest.TestCase):
    def test_restore_and_serve_using_archived_bytes(self):
        with fixture() as source:
            store = object()
            national = {"receipt": {"database_sha256": sha(source)},
                        "pointer": {"release": "bootstrap-123-1"}}

            def manifest(s):
                self.assertIs(s, store)
                return national

            def restore(s, n, dest):
                self.assertIs(s, store)
                self.assertIs(n, national)
                dest.mkdir()
                db = dest / "source.sqlite3"
                db.write_bytes(source.read_bytes())
                return db, {"source_records_total": 1904060}

            with restored_snapshot(store, manifest, restore) as (db, report):
                self.assertTrue(db.is_file())
                result = verify_workspace(db, report)
                self.assertEqual(result["workspace_provider_records"], 1)
                self.assertEqual(result["source"], "private_azure_archive")
                self.assertNotIn("Fixture Hospital", str(result))
                self.assertEqual(sha(db), sha(source))
            self.assertFalse(db.exists())

    def test_digest_drift_stops_before_serving_and_cleans_up(self):
        db = None

        def restore(_, __, dest):
            nonlocal db
            dest.mkdir()
            db = dest / "bad.sqlite3"
            db.write_bytes(b"not the vetted snapshot")
            return db, {"source_records_total": 1904060}

        with self.assertRaisesRegex(ValueError, "workspace database digest"):
            with restored_snapshot(None, lambda _: {"receipt": {"database_sha256": "0" * 64}}, restore):
                self.fail("unverified database reached handler")
        self.assertFalse(db.exists())

    def test_rejects_rebound_host_and_cross_site_navigation(self):
        with fixture() as db, ThreadingHTTPServer(("127.0.0.1", 0), workspace_handler(db, {})) as server:
            t = Thread(target=server.serve_forever, daemon=True)
            t.start()
            try:
                for headers in [{"Host": "foreign.example"}, {"Sec-Fetch-Site": "cross-site"}]:
                    c = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                    try:
                        c.request("GET", "/api/facilities", headers=headers)
                        response = c.getresponse()
                        self.assertEqual(response.status, 403)
                        self.assertNotIn(b"Fixture Hospital", response.read())
                    finally:
                        c.close()
            finally:
                server.shutdown()
                t.join()

    def test_readonly_mode_does_not_create_missing_database(self):
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "no.sqlite3"
            with ThreadingHTTPServer(("127.0.0.1", 0), workspace_handler(missing, {})) as server:
                t = Thread(target=server.serve_forever, daemon=True)
                t.start()
                c = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
                try:
                    c.request("GET", "/api/facilities")
                    self.assertEqual(c.getresponse().status, 500)
                    self.assertFalse(missing.exists())
                finally:
                    c.close()
                    server.shutdown()
                    t.join()
