"""Exercise the compact iQIES create-only contract with a synthetic transport.

Offline fixture seam only. No Azure adapter, credentials, CLI, serving pointer,
existing-object adoption or automatic recovery. Per-object readback is not
proof of atomic storage of the pair, and confers no activation permission.
"""

from hashlib import sha256

from scripts.iqies_compact_release_contract import require, verify_object_readback


class CreateConflict(Exception):
    """The fixture transport definitively rejected the create condition."""


class RehearsalStopped(RuntimeError):
    """The attempted sequence stopped; do not retry or remove anything."""

    def __init__(self, phase, outcome):
        self.phase = phase
        self.outcome = outcome
        super().__init__(f"Compact release rehearsal stopped: {phase}: {outcome}")


def rehearse(plan, payload, manifest, *, create_if_absent, read_range):
    """Use two injected fixture operations, not a live client.

    `create_if_absent(name, data, if_none_match=...)` must apply an atomic
    create condition and return the exact ObjectVersion from that creation.
    Only a definite rejection is a CreateConflict. Any other exception leaves
    the create outcome unknown, even if the fixture actually stored an object.
    `read_range` follows the conditional range contract. There is no pointer
    operation. An interrupted run must remain unverified for separate review.
    """
    inputs = tuple(zip(("payload", "manifest"), plan.create_order, (payload, manifest), strict=True))
    # Reject even a bad manifest before the first simulated create.
    for label, item, data in inputs:
        require(type(data) is bytes and len(data) == item.size
                and sha256(data).hexdigest() == item.digest,
                f"compact {label} input pin mismatch")

    total = 0
    for label, item, data in inputs:
        try:
            version = create_if_absent(item.name, data, if_none_match=item.if_none_match)
        except CreateConflict:
            raise RehearsalStopped(label + "_create", "conflict") from None
        except Exception:
            raise RehearsalStopped(label + "_create", "unknown") from None
        try:
            total += verify_object_readback(item, version, read_range)
        except Exception:
            raise RehearsalStopped(label + "_readback", "not_verified") from None

    return {"rehearsal": "PASS", "objects_verified": 2,
            "bytes_verified": total, "observations": plan.observations}
