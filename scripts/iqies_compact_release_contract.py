"""Offline integrity contract for the already qualified compact iQIES pair.

No transport, credentials, writes, pointer, or serving integration. A future
approved adapter must create the payload with If-None-Match: *, verify it
against the returned version, then create the manifest with the same guard.
After verifying both objects, any update to a serving pointer is a separate
operation. A partial pair or interrupted write is not a release and does not
authorize overwrite, deletion, replay, or a claim of atomic storage. A create
conflict is not permission to replace.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1] / "research"
BLOCK_BYTES = 1024 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}")
BASE_RELEASE = re.compile(r"bootstrap-[0-9]+-[0-9]+")


def require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class CreateOnlyObject:
    name: str
    size: int
    digest: str

    @property
    def if_none_match(self):
        return "*"


@dataclass(frozen=True)
class CompactRelease:
    payload: CreateOnlyObject
    manifest: CreateOnlyObject
    base_release: str
    base_receipt_sha256: str
    base_database_sha256: str
    restored_database_sha256: str
    observations: int

    @property
    def create_order(self):
        # Do not create the manifest until payload readback succeeds.
        return (self.payload, self.manifest)


@dataclass(frozen=True)
class ObjectVersion:
    name: str
    size: int
    etag: str


@dataclass(frozen=True)
class ReadbackRange:
    name: str
    etag: str
    status: int
    start: int
    stop: int  # Exclusive.
    total: int
    body: bytes


def release_plan(roundtrip, national):
    """Cross-check trusted qualification evidence and derive immutable keys."""
    require(type(roundtrip.get("format_version")) is int and roundtrip["format_version"] == 1
            and roundtrip.get("extension_tables_exact_bidirectional_parity") is True
            and roundtrip.get("national_pointer_unchanged") is True,
            "unqualified compact release")
    for key in ("base_release", "base_receipt_sha256", "base_database_sha256",
                "baseline_source_records", "observations"):
        require(key in roundtrip and roundtrip[key] == national.get(key),
                "compact release lineage mismatch")
    base = roundtrip["base_release"]
    require(isinstance(base, str) and BASE_RELEASE.fullmatch(base), "invalid base release")
    candidate = roundtrip.get("qualified_candidate_sha256")
    require(candidate == roundtrip.get("restored_database_sha256")
            == national.get("database_sha256"), "restored database lineage mismatch")
    prior_receipt, base_db, payload_hash, manifest_hash = (
        roundtrip.get(k) for k in ("base_receipt_sha256", "base_database_sha256",
                                   "sidecar_sha256", "manifest_sha256"))
    for digest in (candidate, prior_receipt, base_db, payload_hash, manifest_hash):
        require(isinstance(digest, str) and SHA256.fullmatch(digest), "invalid compact release digest")
    size, manifest_size, count, baseline = (roundtrip.get(k) for k in (
        "sidecar_payload_bytes", "manifest_bytes", "observations", "baseline_source_records"))
    require(all(type(n) is int and n > 0 for n in (size, manifest_size, count, baseline)),
            "invalid compact release size or count")
    manifest = {
        "format_version": 1, "base_database_sha256": base_db,
        "qualified_candidate_sha256": candidate, "sidecar_sha256": payload_hash,
        "sidecar_bytes": size, "observations": count,
    }
    encoded = (json.dumps(manifest, sort_keys=True) + "\n").encode("utf-8")
    require(len(encoded) == manifest_size and sha256(encoded).hexdigest() == manifest_hash,
            "manifest pin does not bind the qualified pair")
    # Relative immutable keys only. No storage account, container, or active path.
    name = f"iqies-services/{manifest_hash}/"
    return CompactRelease(CreateOnlyObject(name + "services.sqlite3", size, payload_hash),
                          CreateOnlyObject(name + "manifest.json", manifest_size, manifest_hash),
                          base, prior_receipt, base_db, candidate, count)


def qualified_plan():
    """Use the retained aggregate proofs, not credentials or private data."""
    pair = json.loads((ROOT / "iqies_sidecar_roundtrip_20261127.json").read_text())["receipt"]
    national = json.loads((ROOT / "iqies_national_service_qualification_20261127.json")
                          .read_text())["receipt"]
    return release_plan(pair, national)


def _check_version(item, version):
    require(isinstance(version, ObjectVersion) and version.name == item.name
            and type(version.size) is int and version.size == item.size
            and isinstance(version.etag, str) and re.fullmatch(r'"[!#-~]+"', version.etag),
            "readback object identity mismatch")


def verify_object_readback(item, version, read_range):
    """Check exact bytes in bounded, version-conditional response ranges.

    `version` comes from the successful create or a separate, authorized
    exact-object inspection. `read_range(item.name, start, stop, if_match=...)`
    returns actual response metadata and MUST cap wire reads before buffering.
    This function never retries or falls back to unversioned/full GET.
    """
    _check_version(item, version)
    digest = sha256()
    for start in range(0, item.size, BLOCK_BYTES):
        stop = min(start + BLOCK_BYTES, item.size)
        reply = read_range(item.name, start, stop, if_match=version.etag)
        require(isinstance(reply, ReadbackRange) and reply.name == item.name
                and reply.etag == version.etag and reply.status == 206
                and all(type(n) is int for n in (reply.status, reply.start, reply.stop, reply.total))
                and (reply.start, reply.stop, reply.total) == (start, stop, item.size)
                and isinstance(reply.body, bytes) and len(reply.body) == stop - start,
                "unqualified compact object readback range")
        digest.update(reply.body)
    require(digest.hexdigest() == item.digest, "compact object checksum mismatch")
    return item.size


def verify_pair_readback(plan, versions, read_range):
    """Check versions, lengths and digests; return aggregate evidence only."""
    require(set(versions) == {obj.name for obj in plan.create_order}, "incomplete compact pair")
    for obj in plan.create_order:
        _check_version(obj, versions[obj.name])
    total = sum(verify_object_readback(obj, versions[obj.name], read_range)
                for obj in plan.create_order)
    return {"objects_verified": 2, "bytes_verified": total, "observations": plan.observations}
