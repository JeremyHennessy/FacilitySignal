from dataclasses import replace
import unittest

from scripts import iqies_compact_release_contract as contract
from scripts import iqies_compact_release_rehearsal as sequence
from test_iqies_compact_release_contract import fixture


class FixtureTransport:
    """Model atomic conditional create, versioned reads, and one-shot faults."""

    def __init__(self):
        self.objects = {}
        self.events = []
        self.lose_ack = None
        self.change_etag = None
        self.damage = None
        self.wrong_ack = None
        self.pointer = "before"

    def create_if_absent(self, name, data, *, if_none_match):
        self.events.append(("create", name, if_none_match))
        if if_none_match != "*":
            raise AssertionError("unguarded fixture write")
        if name in self.objects:
            raise sequence.CreateConflict()
        version = contract.ObjectVersion(name, len(data), f'"version-{len(self.objects) + 1}"')
        self.objects[name] = (data, version)
        if name == self.lose_ack:
            raise TimeoutError("stored locally, acknowledgment deliberately lost")
        if name == self.wrong_ack:
            return replace(version, name="another-object")
        return version

    def read_range(self, name, start, stop, *, if_match):
        self.events.append(("read", name, start, stop, if_match))
        data, version = self.objects[name]
        if name == self.change_etag:
            return contract.ReadbackRange(name, '"different-version"', 412, start, stop, len(data), b"")
        if if_match != version.etag:
            raise AssertionError("unconditional fixture read")
        body = data[start:stop]
        if name == self.damage:
            body = b"!" + body[1:]
        return contract.ReadbackRange(name, version.etag, 206, start, stop, len(data), body)


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.payload, self.manifest, pair, national = fixture()
        self.plan = contract.release_plan(pair, national)
        self.p, self.m = self.plan.payload.name, self.plan.manifest.name
        self.transport = FixtureTransport()

    def run_rehearsal(self, payload=None, manifest=None):
        try:
            return sequence.rehearse(self.plan,
                                      self.payload if payload is None else payload,
                                      self.manifest if manifest is None else manifest,
                                      create_if_absent=self.transport.create_if_absent,
                                      read_range=self.transport.read_range)
        finally:
            self.assertEqual(self.transport.pointer, "before")

    def assert_stops(self, phase, outcome):
        with self.assertRaises(sequence.RehearsalStopped) as event:
            self.run_rehearsal()
        self.assertEqual((event.exception.phase, event.exception.outcome), (phase, outcome))

    def test_verify_payload_version_before_creating_manifest(self):
        result = self.run_rehearsal()
        b = contract.BLOCK_BYTES
        self.assertEqual(self.transport.events, [
            ("create", self.p, "*"),
            ("read", self.p, 0, b, '"version-1"'),
            ("read", self.p, b, 2*b, '"version-1"'),
            ("read", self.p, 2*b, len(self.payload), '"version-1"'),
            ("create", self.m, "*"),
            ("read", self.m, 0, len(self.manifest), '"version-2"'),
        ])
        self.assertEqual(result, {"rehearsal": "PASS", "objects_verified": 2,
                                  "bytes_verified": len(self.payload) + len(self.manifest),
                                  "observations": self.plan.observations})

    def test_both_local_pins_must_match_before_any_transport_call(self):
        for label, kwargs in (("payload", {"payload": b"incorrect"}),
                              ("manifest", {"manifest": b"!" + self.manifest[1:]}),
                              ("manifest", {"manifest": bytearray(self.manifest)})):
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, label + " input pin"):
                self.run_rehearsal(**kwargs)
        self.assertEqual((self.transport.events, self.transport.objects), ([], {}))

    def test_conflict_at_payload_is_a_stop_even_with_same_bytes(self):
        self.transport.objects[self.p] = (self.payload, contract.ObjectVersion(
            self.p, len(self.payload), '"prior"'))
        old = self.transport.objects.copy()
        self.assert_stops("payload_create", "conflict")
        self.assertEqual(self.transport.events, [("create", self.p, "*")])
        self.assertEqual(self.transport.objects, old)

    def test_conflict_at_manifest_never_replaces_or_inspects_existing_manifest(self):
        previous = b"previous marker"
        old = (previous, contract.ObjectVersion(self.m, len(previous), '"prior"'))
        self.transport.objects[self.m] = old
        self.assert_stops("manifest_create", "conflict")
        self.assertEqual(self.transport.events[-1], ("create", self.m, "*"))
        self.assertEqual([event for event in self.transport.events if event[1] == self.m],
                         [("create", self.m, "*")])
        self.assertEqual(self.transport.objects[self.m], old)
        self.assertIn(self.p, self.transport.objects)

    def test_committed_but_lost_ack_is_unknown_at_either_create(self):
        for label, name in (("payload", self.p), ("manifest", self.m)):
            with self.subTest(label=label):
                self.transport = FixtureTransport()
                self.transport.lose_ack = name
                self.assert_stops(label + "_create", "unknown")
                self.assertEqual(self.transport.events[-1], ("create", name, "*"))
                self.assertEqual([event for event in self.transport.events if event[1] == name],
                                 [("create", name, "*")])
                self.assertIn(name, self.transport.objects)
                self.assertEqual(self.m in self.transport.objects, name == self.m)

    def test_payload_drift_or_wrong_ack_stops_before_manifest_create(self):
        for fault in ("change_etag", "damage", "wrong_ack"):
            with self.subTest(fault=fault):
                self.transport = FixtureTransport()
                setattr(self.transport, fault, self.p)
                self.assert_stops("payload_readback", "not_verified")
                self.assertTrue(all(event[1] == self.p for event in self.transport.events))
                reads = [event for event in self.transport.events if event[0] == "read"]
                self.assertEqual(len(reads), {"change_etag": 1, "damage": 3, "wrong_ack": 0}[fault])

    def test_manifest_readback_failure_issues_no_pass_or_retry(self):
        self.transport.change_etag = self.m
        self.assert_stops("manifest_readback", "not_verified")
        self.assertEqual(self.transport.events[-2:], [
            ("create", self.m, "*"), ("read", self.m, 0, len(self.manifest), '"version-2"')])
        self.assertEqual(len(self.transport.events), 6)
        self.assertEqual(set(self.transport.objects), {self.p, self.m})
