from dataclasses import replace
from hashlib import sha256
import json
import unittest

from scripts import iqies_compact_release_contract as contract


def fixture():
    payload = b"x" * (2 * contract.BLOCK_BYTES + 3)
    base = "1" * 64
    candidate = "2" * 64
    payload_hash = sha256(payload).hexdigest()
    manifest = (json.dumps({
        "format_version": 1, "base_database_sha256": base,
        "qualified_candidate_sha256": candidate, "sidecar_sha256": payload_hash,
        "sidecar_bytes": len(payload), "observations": 17,
    }, sort_keys=True) + "\n").encode()
    national = {
        "base_release": "bootstrap-123-1", "database_sha256": candidate,
        "base_database_sha256": base, "base_receipt_sha256": "3" * 64,
        "baseline_source_records": 42, "observations": 17,
    }
    roundtrip = {
        **national, "format_version": 1, "extension_tables_exact_bidirectional_parity": True,
        "national_pointer_unchanged": True, "qualified_candidate_sha256": candidate,
        "restored_database_sha256": candidate, "sidecar_sha256": payload_hash,
        "manifest_sha256": sha256(manifest).hexdigest(), "sidecar_payload_bytes": len(payload),
        "manifest_bytes": len(manifest),
    }
    return payload, manifest, roundtrip, national


class ReleaseContractTests(unittest.TestCase):
    def setUp(self):
        self.payload, self.manifest, self.roundtrip, self.national = fixture()
        self.plan = contract.release_plan(self.roundtrip, self.national)
        self.parts = {self.plan.payload.name: self.payload, self.plan.manifest.name: self.manifest}
        self.versions = {obj.name: contract.ObjectVersion(obj.name, obj.size, f'"v{i}"')
                         for i, obj in enumerate(self.plan.create_order)}
        self.calls = []

    def response(self, name, start, stop, *, if_match):
        self.calls.append((name, start, stop, if_match))
        data = self.parts[name]
        return contract.ReadbackRange(name, self.versions[name].etag, 206,
                                      start, stop, len(data), data[start:stop])

    def test_real_receipts_reproduce_exact_manifest_and_create_only_plan(self):
        plan = contract.qualified_plan()
        self.assertEqual(plan.base_release, "bootstrap-45845760984-1")
        self.assertEqual(plan.base_receipt_sha256,
                         "6fbcdfb7f1e4491b0874127ded141dd58e0fef95fe2dec57be64f0469167ab9e")
        self.assertEqual(plan.base_database_sha256,
                         "138ad57c3719fe63895eeaff702c04b51107fe1cf6dc4daf403a554985a1f033")
        self.assertEqual(plan.observations, 93913)
        self.assertEqual(plan.restored_database_sha256,
                         "28f90c1b3e2d2b0fe5c800ff2da671df320748f00e9e333dbbf0ca84d21db3d3")
        self.assertEqual([obj.size for obj in plan.create_order], [12685312, 348])
        self.assertEqual([obj.if_none_match for obj in plan.create_order], ["*", "*"])
        self.assertEqual(plan.payload.digest,
                         "ab64fdc8d36b6066788d1bfd9f565ec181e9a2df4d5c01387d3f749040b1c253")
        self.assertEqual(plan.manifest.digest,
                         "a1a777e3e88962a37bed981e931af42d5155b522e2dbcfb4aa20903ac4ff820d")
        self.assertEqual([obj.name for obj in plan.create_order],
                         [f"iqies-services/{plan.manifest.digest}/" + leaf
                          for leaf in ("services.sqlite3", "manifest.json")])

    def test_receipt_and_manifest_lineage_requirements(self):
        for field, value in (("format_version", True), ("base_release", "bootstrap-123-2"), ("observations", 18),
                             ("base_receipt_sha256", "4" * 64),
                             ("extension_tables_exact_bidirectional_parity", False),
                             ("national_pointer_unchanged", False),
                             ("restored_database_sha256", "4" * 64),
                             ("manifest_bytes", self.roundtrip["manifest_bytes"] + 1),
                             ("sidecar_sha256", "4" * 64)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                contract.release_plan({**self.roundtrip, field: value}, self.national)
        for field in ("base_release", "base_receipt_sha256", "database_sha256"):
            with self.subTest(absent=field), self.assertRaises(ValueError):
                contract.release_plan(self.roundtrip, {k: v for k, v in self.national.items() if k != field})

    def test_pair_supports_only_exact_bounded_versioned_ranges(self):
        result = contract.verify_pair_readback(self.plan, self.versions, self.response)
        p = self.plan.payload.name
        m = self.plan.manifest.name
        b = contract.BLOCK_BYTES
        self.assertEqual(self.calls, [(p, 0, b, '"v0"'), (p, b, 2*b, '"v0"'),
                                      (p, 2*b, 2*b+3, '"v0"'), (m, 0, len(self.manifest), '"v1"')])
        self.assertEqual(result, {"bytes_verified": len(self.payload) + len(self.manifest),
                                  "objects_verified": 2, "observations": 17})

    def test_partial_or_wrong_version_metadata_rejected_before_fetch(self):
        name = self.plan.manifest.name
        version = self.versions[name]
        for case in ({}, {**self.versions, "other": version},
                     {**self.versions, name: replace(version, name="other")},
                     {**self.versions, name: replace(version, size=version.size + 1)},
                     {**self.versions, name: replace(version, etag='W/"v1"')},
                     {**self.versions, name: replace(version, etag="*")}):
            with self.assertRaises(ValueError):
                contract.verify_pair_readback(self.plan, case, self.response)
        self.assertEqual(self.calls, [])

    def test_unqualified_response_stops_without_retry(self):
        b = contract.BLOCK_BYTES
        for drift in ({"status": 200}, {"status": 412}, {"etag": '"changed"'},
                      {"name": "different"}, {"start": 1}, {"stop": b - 1},
                      {"total": len(self.payload) + 1},
                      {"body": b"x" * (b + 1)}, {"body": b""}):
            self.calls.clear()

            def bad_response(*args, **kwargs):
                return replace(self.response(*args, **kwargs), **drift)

            with self.subTest(drift=tuple(drift)), self.assertRaisesRegex(ValueError, "readback range"):
                contract.verify_pair_readback(self.plan, self.versions, bad_response)
            self.assertEqual(len(self.calls), 1)

    def test_same_size_tampering_in_either_object_rejected(self):
        for obj in self.plan.create_order:
            with self.subTest(object=obj.name):
                old = self.parts[obj.name]
                self.parts[obj.name] = b"!" + old[1:]
                self.calls.clear()
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    contract.verify_pair_readback(self.plan, self.versions, self.response)
                self.parts[obj.name] = old
                if obj == self.plan.payload:
                    self.assertNotIn(self.plan.manifest.name, [call[0] for call in self.calls])
