from contextlib import closing, contextmanager
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import ModuleType
import unittest
from unittest.mock import patch

import facilitysignal
from iqies_capabilities import DDL
from build_combined import sha
from scripts.azure_private_workspace import cached_snapshot, restored_snapshot, verify_workspace, workspace_handler, with_service_sidecar


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
        with closing(facilitysignal.connect(db)) as con:
            con.executescript(DDL)
            con.execute("INSERT INTO certification_releases VALUES(?,?,?,?,?,?,?,?,?)",
                        ("iqies","Fixture","2026-Q3","fixture-api","fixture-csv","a"*64,1,"2026-11-01","{}"))
            con.execute("INSERT INTO certification_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        ("iqies",1,"b"*64,"000002","Fixture ASC","2 Example Street",
                         "Test City","NY","10002","Ambulatory surgical center","","","",""))
            con.execute("INSERT INTO iqies_capability_release VALUES(?,?,?,?,?,?,?)",
                        (1,"a"*64,"b"*64,"2026-Q3","fixture-dictionary",1,"2026-11-01"))
            con.execute("INSERT INTO iqies_capability_observations VALUES(?,?,?,?,?,?)",
                        ("iqies",1,"oprtg_room_cnt","ASC","reported_count",2))
            con.commit()
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
                self.assertEqual(result["filtered_provider_records"], 1)
                self.assertEqual(result["service_observations"], 1)
                self.assertTrue(result["provider_profile_verified"])
                self.assertTrue(result["snapshot_unchanged"])
                self.assertEqual(result["source"], "private_azure_archive")
                self.assertNotIn("Fixture Hospital", str(result))
                self.assertEqual(sha(db), sha(source))
            self.assertFalse(db.exists())

    def test_http_count_drift_is_not_certified(self):
        with fixture() as db:
            def wrong_service(_db, _params):
                return {"status":"source_observations","total":2,"rows":[{"state":"NY"}]}
            with patch("local_research.service_search", side_effect=wrong_service):
                with self.assertRaisesRegex(ValueError, "service search differs"):
                    verify_workspace(db, {})

    def test_local_copy_replays_exact_export_and_rejects_wrong_digest(self):
        with fixture() as source:
            digest = sha(source)
            pin = {"release": "bootstrap-123-1", "reconstruction_audit": {
                "source_records_total": 1904060, "database_bytes": source.stat().st_size,
                "database_sha256": digest}}
            with cached_snapshot(source, pin) as (db, report):
                self.assertNotEqual(db, source)
                self.assertEqual(verify_workspace(db, report)["http_smoke"], "PASS")
                self.assertEqual(report["source"], "verified_local_copy_of_private_azure_archive")
            self.assertFalse(db.exists())
            self.assertEqual(sha(source), digest)
            pin["reconstruction_audit"]["database_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "workspace cache digest"):
                with cached_snapshot(source, pin):
                    self.fail("wrong snapshot was opened")

    def test_sidecar_rejects_changed_bytes_before_restore_and_cleans_output(self):
        with fixture() as base, TemporaryDirectory() as tmp:
            home = Path(tmp)
            sidecar = home / "hold"
            sidecar.mkdir()
            manifest = sidecar / "manifest.json"
            pack = sidecar / "services.sqlite3"
            manifest.write_text("{}")
            pack.write_bytes(b"fixture")
            proof = home / "proof.json"
            expected = {"base_release":"bootstrap-123-1","base_database_sha256":sha(base),
                        "manifest_bytes":manifest.stat().st_size,"manifest_sha256":sha(manifest),
                        "sidecar_payload_bytes":pack.stat().st_size,"sidecar_sha256":sha(pack),
                        "restored_database_sha256":"c"*64, "observations":3}
            proof.write_text(json.dumps({"receipt":expected}))
            mod = ModuleType("scripts.iqies_service_sidecar")

            def restore(src, path, out, pin):
                self.assertEqual((src,path,pin),(base,sidecar,sha(manifest)))
                out.write_bytes(b"test restore result")
                return {"database_sha256":"c"*64,"observations":3,"base_preserved":True}

            mod.restore = restore
            report = {"release":expected["base_release"]}
            with patch.dict("sys.modules", {"scripts.iqies_service_sidecar":mod}), patch(
                    "private_iqies_service_research.ROUNDTRIP", proof):
                with with_service_sidecar(base,report,sidecar) as (out, got):
                    self.assertTrue(out.is_file())
                    self.assertEqual(got["qualified_service_extension_observations"],3)
                self.assertFalse(out.exists())
                pack.write_bytes(b"altered")
                with self.assertRaisesRegex(ValueError, "service sidecar pin"):
                    with with_service_sidecar(base,report,sidecar):
                        self.fail("changed sidecar was opened")

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
