"""Narrow follow-up of shared-CCN hospital/LTCH reported-address discrepancies.
No canonical merge, geocoding, new match discovery, or source modification.
"""
import json
from collections import Counter
from scripts.public_identity_candidate_audit import load, norm, complete_address, require, ROOT


def classify(hospital, ltch):
    if not hospital.get("ccn") or hospital["ccn"] != ltch.get("ccn"):
        return "different_identifier"
    h, l = complete_address(hospital), complete_address(ltch)
    if h is None or l is None:
        return "incomplete_address"
    if h == l:
        return "exact_reported_address"
    if h[1:] != l[1:]:
        return "city_state_or_zip_discrepancy"
    name = norm(hospital.get("name"))
    if not name or name != norm(ltch.get("name")):
        return "name_discrepancy"
    # One literal standalone terminal hyphen only, in the observed direction.
    # Never remove suite/floor detail, interior punctuation, or ZIP suffixes.
    if l[0] == h[0] + " -" and not h[0].endswith("-"):
        return "ltch_terminal_hyphen_only"
    return "other_street_discrepancy"


def adjudicate(packs):
    def index(source):
        rows = packs[source]["records"]
        require(packs[source]["source"] == source and packs[source]["row_count"] == len(rows), "source membership mismatch")
        result = {r["ccn"]: r for r in rows}
        require(len(result) == len(rows) and all(result), "nonunique or missing CCN")
        return result

    hospital, ltch = index("hospital"), index("long-term-hospital")
    counts = Counter(classify(hospital[k], ltch[k]) for k in hospital.keys() & ltch.keys())
    return {"scope": "Same exact CCN within pinned hospital and LTCH sources only; formatting evidence, not physical-site verification or entity merge.", "hospital_rows": len(hospital), "ltch_rows": len(ltch), "shared_ccn_pairs": sum(counts.values()), "classification_counts": dict(sorted(counts.items())), "canonical_merges": 0}


def qualified(root=ROOT):
    packs, pins = load(root)
    return {**adjudicate(packs), "source_pins": {key: pins[key] for key in ("hospital", "long-term-hospital")}}


if __name__ == "__main__":
    print("FACILITYSIGNAL_HOSPITAL_LTCH_ADJUDICATION", json.dumps(qualified(), sort_keys=True), flush=True)
