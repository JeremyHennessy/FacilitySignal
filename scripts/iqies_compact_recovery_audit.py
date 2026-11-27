"""Read-only offline audit of an interrupted compact iQIES rehearsal.

Use only exact acknowledged versions or separately inspected synthetic
evidence from the two planned object keys. Never create, delete, inspect a
prefix, adopt a pair, or touch a pointer. Even an exact pair verifies only
the supplied versions, not write history, atomicity, or activation rights.
"""

from dataclasses import dataclass

from scripts.iqies_compact_release_contract import (
    ObjectVersion,
    verify_object_readback,
    verify_pair_readback,
)


@dataclass(frozen=True)
class InspectedAbsent:
    """The caller's separate exact-key inspection confirmed absence."""
    name: str


def _result(state, reason, objects=0, bytes_verified=0):
    return {"state": state, "reason": reason, "objects_verified": objects,
            "bytes_verified": bytes_verified, "activation_authorized": False}


def audit_pair(plan, inspections, read_range, *, acknowledged=None):
    """Classify the exact pair without writing or retrying.

    `inspections` maps exact planned keys to an ObjectVersion or an
    InspectedAbsent. Omission is unknown, never proof of absence. Optional
    `acknowledged` maps planned keys to the versions actually acknowledged
    by creation. An inspection cannot replace a different acknowledged
    version or explain a timeout. No inspection is performed here.
    """
    acknowledged = {} if acknowledged is None else acknowledged
    payload, manifest = plan.create_order
    names = {payload.name, manifest.name}
    if (set(inspections) | set(acknowledged)) - names:
        return _result("malformed_or_stale", "unexpected_object_identity")

    versions, absent = {}, set()
    for item in (payload, manifest):
        key = item.name
        if key in acknowledged and not isinstance(acknowledged[key], ObjectVersion):
            return _result("malformed_or_stale", "invalid_acknowledged_version")
        if key in inspections and not isinstance(inspections[key], (ObjectVersion, InspectedAbsent)):
            return _result("unverified", "inspection_unavailable")
        if key in inspections and key in acknowledged and inspections[key] != acknowledged[key]:
            return _result("malformed_or_stale", "inspection_disagrees_with_acknowledgment")
        evidence = inspections.get(key, acknowledged.get(key))
        if evidence is None:
            return _result("unverified", "missing_inspection_or_acknowledgment")
        if evidence.name != key:
            return _result("malformed_or_stale", "unexpected_object_identity")
        if isinstance(evidence, InspectedAbsent):
            absent.add(key)
        else:
            versions[key] = evidence

    if absent == names:
        return _result("missing_both", "two_explicit_absences")
    if payload.name in absent:
        return _result("malformed_or_stale", "manifest_without_payload")

    try:
        if manifest.name in absent:
            size = verify_object_readback(payload, versions[payload.name], read_range)
            return _result("payload_only", "exact_payload_and_explicit_manifest_absence", 1, size)
        check = verify_pair_readback(plan, versions, read_range)
        return _result("complete_exact", "exact_versions_verified",
                       check["objects_verified"], check["bytes_verified"])
    except ValueError:
        return _result("malformed_or_stale", "version_or_bytes_not_verified")
    except Exception:
        return _result("unverified", "readback_unavailable")
