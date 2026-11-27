"""Qualify compact iQIES sidecar recovery from exact national inputs.

One controlled reconstruction and loopback app smoke; no archive writes,
pointer mutations, raw artifacts, or public projections. Only a small
aggregate receipt may leave the temporary runner directory.
"""
import argparse
import json
import os
import tempfile
from contextlib import closing
from pathlib import Path

import azure_national_archive as archive
from build_combined import require, readonly, sha
from scripts import iqies_service_sidecar as sidecar
from scripts import qualify_iqies_national_services as national
from scripts import azure_verified_extension as ext
from scripts.azure_private_workspace import verify_workspace


class ReadOnlyStore:
    """Expose only the methods needed to restore the existing private snapshot."""
    def __init__(self, store):
        self._store = store

    def private(self):
        return self._store.private()

    def head(self, name):
        return self._store.head(name)

    def chunks(self, name, etag):
        return self._store.chunks(name, etag)


def qualify(store, root):
    root = Path(root)
    before = ext.national_manifest(store)
    expected = sidecar.pinned_receipt()
    require(before["receipt_sha256"] == expected["base_receipt_sha256"],
            "qualified national receipt changed")
    require(before["pointer"]["release"] == expected["base_release"]
            and before["receipt"]["database_sha256"] == expected["base_database_sha256"],
            "qualified national base lineage changed")
    rebuilt = national.run(store, root)
    require(rebuilt == expected, "reconstructed qualification receipt differs")
    base = root / "base" / "facilitysignal.sqlite3"
    candidate = root / "candidate" / "facilitysignal.sqlite3"
    pack = root / "service-sidecar"
    restored = root / "restored.sqlite3"
    manifest = sidecar.export(base, candidate, pack)
    pin = sha(pack / "manifest.json")
    recovery = sidecar.restore(base, pack, restored, pin)
    # Compare actual rows, not only state totals. SQLite byte layouts need not
    # be identical after restoration.
    with closing(readonly(restored)) as db:
        db.execute("ATTACH DATABASE ? AS candidate",
                   (candidate.resolve().as_uri() + "?mode=ro&immutable=1",))
        sidecar.compare_rows(db, "main", "candidate")
    require(sha(base) == expected["base_database_sha256"], "base changed")
    require(sha(candidate) == expected["database_sha256"], "candidate changed")
    require(sha(pack / "manifest.json") == pin, "manifest changed")
    require(sha(pack / "services.sqlite3") == manifest["sidecar_sha256"],
            "sidecar changed")
    require(recovery["observations"] == expected["observations"]
            and recovery["base_preserved"], "recovery receipt mismatch")
    require(recovery["database_sha256"] == sha(restored), "restored hash mismatch")
    # The extension's actual handler verifies the retained restored-db pin
    # at startup. Serve this very file, not a second restore or a base-only
    # copy. Keep provider rows in loopback responses, never in the receipt.
    restored.chmod(0o400)
    workspace_smoke = verify_workspace(restored, {
        "source": "private_azure_archive",
        "release": expected["base_release"],
        "source_records": expected["baseline_source_records"],
        "read_only": True,
        "qualified_service_extension_observations": recovery["observations"],
    })
    ext.unchanged(store, before)
    return {
        "format_version": 1,
        "scope": "Temporary full national sidecar round-trip and loopback app smoke; aggregate evidence only",
        "base_release": expected["base_release"],
        "base_receipt_sha256": expected["base_receipt_sha256"],
        "base_database_sha256": expected["base_database_sha256"],
        "qualified_candidate_sha256": expected["database_sha256"],
        "restored_database_sha256": recovery["database_sha256"],
        "base_database_bytes": base.stat().st_size,
        "sidecar_payload_bytes": manifest["sidecar_bytes"],
        "manifest_bytes": (pack / "manifest.json").stat().st_size,
        "sidecar_sha256": manifest["sidecar_sha256"],
        "manifest_sha256": pin,
        "observations": recovery["observations"],
        "field_states": expected["field_states"],
        "service_states": expected["service_states"],
        "source_record_filter_checks": expected["source_record_filter_checks"],
        "baseline_tables_preserved": expected["unchanged_base_tables"],
        "baseline_source_records": expected["baseline_source_records"],
        "extension_tables_exact_bidirectional_parity": True,
        "workspace_smoke": workspace_smoke,
        "national_pointer_unchanged": True,
        "private_storage_written": False,
        "public_promotion": False,
        "storage_cost_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    require(not args.receipt.exists(), "receipt exists")
    archive.run_key(os.environ)
    store = archive.Azure(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="iqies-sidecar-private-",
                                         dir=os.environ.get("RUNNER_TEMP")) as tmp:
            result = qualify(ReadOnlyStore(store), Path(tmp))
    finally:
        store.close()
    with args.receipt.open("xb") as out:
        out.write(archive.encode(result))
    print("IQIES_NATIONAL_SIDECAR_ROUNDTRIP", json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
