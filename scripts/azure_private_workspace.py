"""Serve a verified national Azure snapshot in the loopback-only app.

Never initializes a source database or exposes Azure connection information.
Azure recovery reuses the existing trusted-main storage boundary.
"""
import argparse
from contextlib import closing, contextmanager
from html import escape
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from threading import Thread
from urllib.parse import urlencode
from urllib.request import urlopen

import facilitysignal
from build_combined import require, sha


@contextmanager
def restored_snapshot(store, national_manifest, restore_national):
    national = national_manifest(store)
    with tempfile.TemporaryDirectory(prefix="facilitysignal-azure-workspace-") as work:
        db, audit = restore_national(store, national, Path(work) / "verified")
        receipt = national["receipt"]
        require(sha(db) == receipt["database_sha256"], "workspace database digest")
        report = {
            "source": "private_azure_archive",
            "release": national["pointer"]["release"],
            "source_records": audit["source_records_total"],
            "read_only": True,
        }
        require(re.fullmatch(r"bootstrap-[0-9]+-[0-9]+", report["release"]) is not None,
                "workspace release format")
        require(report["source_records"] == 1904060, "workspace archive scope")
        db.chmod(0o400)
        yield db, report


def workspace_handler(db, report):
    base = facilitysignal.handler(db, readonly_snapshot=True)

    class WorkspaceHandler(base):
        def log_message(self, *_):
            # Do not echo path/query/provider data into workflow logs.
            pass

        def do_GET(self):
            if (self.headers.get_all("Host") != ["127.0.0.1:" + str(self.server.server_port)]
                    or self.headers.get("Sec-Fetch-Site") == "cross-site"):
                return self.send(403, "Loopback workspace only", "text/plain; charset=utf-8")
            if self.path == "/api/archive":
                return self.send(200, json.dumps(report), "application/json; charset=utf-8")
            return super().do_GET()

        def send(self, status, data, content_type):
            if self.path == "/" and status == 200 and content_type.startswith("text/html"):
                note = ('<p><strong>Private Azure snapshot · read-only</strong> '
                        '<a href="/api/archive">Archive provenance</a></p>')
                # Insert after the generated <main> element starts, before user-facing data.
                data, changed = re.subn(r"(<main(?:\s[^>]+)?>)", r"\g<1>" + note, data, count=1)
                if changed != 1:
                    return super().send(500, "Workspace layout unavailable", "text/plain; charset=utf-8")
            return super().send(status, data, content_type)

    return WorkspaceHandler


def verify_workspace(db, report):
    """Hit the actual UI and existing read-only service, emitting no provider rows."""
    digest = sha(db)
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as sql:
        provider = sql.execute("""SELECT f.ccn,f.name,f.state,r.published_on
            FROM facilities f JOIN releases r ON f.release_id=r.id
            WHERE f.dataset='hospital' ORDER BY f.ccn LIMIT 1""").fetchone()
        require(provider is not None, "no hospital profile available")
        ccn, name, state, release = provider
        provider_count = sql.execute(
            "SELECT count(*) FROM facilities WHERE dataset='hospital' AND state=? AND ccn=?",
            (state, ccn)).fetchone()[0]
        jurisdictions = sorted(facilitysignal.STATES)
        placeholders = ",".join("?" for _ in jurisdictions)
        service_state = sql.execute("""SELECT min(c.state)
            FROM iqies_capability_observations o JOIN certification_records c
              ON o.registry=c.registry AND o.row_number=c.row_number
            WHERE o.registry='iqies' AND o.field='oprtg_room_cnt'
              AND o.provider_scope='ASC' AND c.state IN (""" + placeholders + ")",
              jurisdictions).fetchone()[0]
        require(service_state in facilitysignal.STATES, "no scoped service observations")
        service_count = sql.execute("""SELECT count(*)
            FROM iqies_capability_observations o JOIN certification_records c
              ON o.registry=c.registry AND o.row_number=c.row_number
            WHERE o.registry='iqies' AND o.field='oprtg_room_cnt'
              AND o.provider_scope='ASC' AND c.state=?""", (service_state,)).fetchone()[0]
        require(provider_count == 1 and service_count > 0, "snapshot route inputs incomplete")
    with ThreadingHTTPServer(("127.0.0.1", 0), workspace_handler(db, report)) as server:
        t = Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            with urlopen(origin + "/", timeout=20) as resp:
                require(b"Private Azure snapshot" in resp.read(), "workspace HTML")
            with urlopen(origin + "/api/archive", timeout=20) as resp:
                require(json.load(resp) == report, "workspace archive lineage")
            filters = {"dataset": "hospital", "state": state, "ccn": ccn, "limit": 1}
            with urlopen(origin + "/api/facilities?" + urlencode(filters), timeout=20) as resp:
                data = json.load(resp)
                require(data["total"] == provider_count and len(data["rows"]) == 1
                        and all(data["rows"][0][k] == v for k,v in (
                            ("ccn", ccn), ("name", name), ("state", state), ("dataset", "hospital"))),
                        "filtered provider search differs from snapshot")
            with urlopen(origin + "/facility?" + urlencode({"dataset": "hospital", "ccn": ccn}),
                         timeout=20) as resp:
                page = resp.read().decode()
                require("<h1>" + escape(name) + "</h1>" in page
                        and "<strong>" + escape(release) + "</strong>" in page,
                        "provider profile differs from snapshot")
            svc = {"registry": "iqies", "field": "oprtg_room_cnt", "state": service_state, "limit": 1}
            with urlopen(origin + "/api/service-research?" + urlencode(svc), timeout=20) as resp:
                data = json.load(resp)
                require(data["status"] == "source_observations" and data["total"] == service_count
                        and len(data["rows"]) == 1 and data["rows"][0]["state"] == service_state,
                        "service search differs from snapshot")
            require(sha(db) == digest, "snapshot changed during workspace smoke")
            return {**report, "filtered_provider_records": provider_count, "service_observations": service_count,
                    "provider_profile_verified": True, "snapshot_unchanged": True, "http_smoke": "PASS"}
        finally:
            server.shutdown()
            t.join()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--verify-only", action="store_true",
                   help="Run an HTTP smoke check and output an aggregate receipt, then exit")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()
    try:
        from azure_national_archive import run_key
        from scripts.audit_azure_archive_inventory import ReadOnlyAzure
        from scripts.azure_verified_extension import national_manifest, restore_national

        run_key(os.environ)
        store = ReadOnlyAzure(os.environ)
        try:
            with restored_snapshot(store, national_manifest, restore_national) as (db, report):
                if args.verify_only:
                    print(json.dumps(verify_workspace(db, report), sort_keys=True), flush=True)
                else:
                    with ThreadingHTTPServer(("127.0.0.1", args.port),
                                             workspace_handler(db, report)) as server:
                        print(f"Private FacilitySignal: http://127.0.0.1:{server.server_port}/", flush=True)
                        server.serve_forever()
        finally:
            store.close()
    except (ValueError, OSError, ImportError):
        p.exit(1, "Private Azure workspace failed validation or could not start.\n")
    except Exception:
        # Azure SDK failures can contain request details. Do not print them.
        p.exit(1, "Private Azure workspace could not verify the authorized archive.\n")


if __name__ == "__main__":
    main()
