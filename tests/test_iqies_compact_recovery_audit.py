from dataclasses import replace
from unittest import TestCase

from scripts import iqies_compact_recovery_audit as recovery
from scripts import iqies_compact_release_contract as contract
from scripts import iqies_compact_release_rehearsal as rehearsal
from test_iqies_compact_release_contract import fixture
from test_iqies_compact_release_rehearsal import FixtureTransport


class RecoveryAuditTests(TestCase):
    def setUp(self):
        self.payload, self.manifest, r, n = fixture()
        self.plan = contract.release_plan(r, n)
        self.p, self.m = self.plan.payload.name, self.plan.manifest.name
        self.transport = FixtureTransport()
        self.acks = {}

    def create(self, name, data, *, if_none_match):
        version = self.transport.create_if_absent(name, data, if_none_match=if_none_match)
        self.acks[name] = version
        return version

    def attempt(self, lost=None):
        self.transport.lose_ack = lost

        def run():
            return rehearsal.rehearse(self.plan, self.payload, self.manifest,
                                      create_if_absent=self.create, read_range=self.transport.read_range)
        if lost is None:
            run()
        else:
            with self.assertRaises(rehearsal.RehearsalStopped) as outcome:
                run()
            self.assertEqual(outcome.exception.outcome, "unknown")
        self.transport.events.clear()

    def separately_inspected(self):
        # Deliberately outside the audit and writer: two exact synthetic keys,
        # no prefix listing, and explicit evidence for absence.
        return {name: (self.transport.objects[name][1] if name in self.transport.objects
                       else recovery.InspectedAbsent(name))
                for name in (self.p, self.m)}

    def audit(self, evidence, reader=None, *, use_acks=True):
        old_objects = self.transport.objects.copy()
        result = recovery.audit_pair(self.plan, evidence,
                                     reader or self.transport.read_range,
                                     acknowledged=self.acks if use_acks else None)
        self.assertFalse(result["activation_authorized"])
        self.assertEqual((self.transport.objects, self.transport.pointer), (old_objects, "before"))
        self.assertTrue(all(e[0] == "read" for e in self.transport.events))
        return result

    def test_missing_both_requires_two_explicit_absences(self):
        self.assertEqual(self.audit({})["state"], "unverified")
        self.assertEqual(self.audit({self.p: recovery.InspectedAbsent(self.p)})["state"], "unverified")
        self.assertEqual(self.audit(self.separately_inspected()), {
            "state": "missing_both", "reason": "two_explicit_absences", "objects_verified": 0,
            "bytes_verified": 0, "activation_authorized": False,
        })
        self.assertEqual(self.transport.events, [])

    def test_lost_payload_ack_is_unknown_until_separate_exact_inspection(self):
        self.attempt(lost=self.p)
        self.assertEqual(self.acks, {})
        self.assertEqual(self.audit({})["state"], "unverified")
        self.assertEqual(self.transport.events, [])
        result = self.audit(self.separately_inspected())
        self.assertEqual(result, {
            "state": "payload_only", "reason": "exact_payload_and_explicit_manifest_absence",
            "objects_verified": 1, "bytes_verified": len(self.payload), "activation_authorized": False,
        })
        self.assertEqual([e[1] for e in self.transport.events], [self.p] * 3)
        self.assertEqual(self.acks, {})  # Evidence does not become a create acknowledgment.

    def test_lost_manifest_ack_never_invents_ack_even_when_complete_exact(self):
        self.attempt(lost=self.m)
        self.assertEqual(set(self.acks), {self.p})
        self.assertEqual(self.audit({})["state"], "unverified")
        self.assertEqual(self.transport.events, [])
        result = self.audit(self.separately_inspected())
        self.assertEqual(result["state"], "complete_exact")
        self.assertEqual(result["objects_verified"], 2)
        self.assertEqual(result["bytes_verified"], len(self.payload) + len(self.manifest))
        self.assertEqual(set(self.acks), {self.p})

    def test_exact_acknowledged_ids_need_no_discovery(self):
        self.attempt()
        self.assertEqual(self.audit({})["state"], "complete_exact")
        self.assertEqual([e[1] for e in self.transport.events], [self.p] * 3 + [self.m])
        self.assertTrue(all(e[-1] == self.acks[e[1]].etag for e in self.transport.events))

    def test_inspection_never_replaces_an_acknowledged_version(self):
        self.attempt()
        evidence = self.separately_inspected()
        for replacement in (replace(evidence[self.p], etag='"later-but-same-size"'),
                            recovery.InspectedAbsent(self.p)):
            with self.subTest(replacement=replacement):
                result = self.audit({**evidence, self.p: replacement})
                self.assertEqual(result["state"], "malformed_or_stale")
                self.assertEqual(result["reason"], "inspection_disagrees_with_acknowledgment")
        self.assertEqual(self.transport.events, [])

    def test_manifest_only_and_unexpected_keys_are_not_candidates(self):
        self.transport.objects[self.m] = (self.manifest, contract.ObjectVersion(
            self.m, len(self.manifest), '"orphan"'))
        evidence = self.separately_inspected()
        self.assertEqual(self.audit(evidence)["reason"], "manifest_without_payload")
        self.assertEqual(self.audit({**evidence, "other": None})["reason"], "unexpected_object_identity")
        self.assertEqual(self.audit({**evidence, self.p: None})["state"], "unverified")
        self.assertEqual(self.transport.events, [])

    def test_stale_or_corrupted_readback_is_not_retried_or_treated_as_missing(self):
        self.attempt()
        self.transport.change_etag = self.p
        result = self.audit({})
        self.assertEqual(result["state"], "malformed_or_stale")
        self.assertEqual(len(self.transport.events), 1)
        self.transport.events.clear()
        self.transport.change_etag = None
        self.transport.damage = self.m
        self.assertEqual(self.audit({})["state"], "malformed_or_stale")
        self.assertEqual([e[1] for e in self.transport.events], [self.p] * 3 + [self.m])

    def test_transport_unavailable_is_not_absence(self):
        self.attempt()

        def unavailable(name, start, stop, *, if_match):
            self.transport.events.append(("read", name, start, stop, if_match))
            raise TimeoutError("unknown")

        self.assertEqual(self.audit({}, unavailable)["state"], "unverified")
        self.assertEqual(len(self.transport.events), 1)
