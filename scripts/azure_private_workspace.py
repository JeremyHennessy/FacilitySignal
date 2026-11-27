"""Serve a verified national Azure snapshot in the loopback-only app.

Never initializes a source database or exposes Azure connection information.
Azure recovery reuses the existing trusted-main storage boundary.
"""
import argparse
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import tempfile
from threading import Thread
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
    with ThreadingHTTPServer(("127.0.0.1", 0), workspace_handler(db, report)) as server:
        t = Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            with urlopen(origin + "/", timeout=20) as resp:
                require(b"Private Azure snapshot" in resp.read(), "workspace HTML")
            with urlopen(origin + "/api/archive", timeout=20) as resp:
                require(json.load(resp) == report, "workspace archive lineage")
            with urlopen(origin + "/api/facilities?limit=1", timeout=20) as resp:
                data = json.load(resp)
                require(data["total"] > 0, "workspace has no usable provider records")
            return {**report, "workspace_provider_records": data["total"], "http_smoke": "PASS"}
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
