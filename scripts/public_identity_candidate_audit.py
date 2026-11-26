"""Audit exact cross-program identity evidence in already approved public packs.
Only source-scoped candidate pair counts leave memory. No canonical site merge.
"""
import argparse
import hashlib
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_PAIRS = 1_000_000
FIELDS = ("address", "city", "state", "zip")

def require(ok, message):
    if not ok:
        raise ValueError(message)

def norm(value):
    return " ".join(value.upper().split()) if isinstance(value, str) else ""

def complete_address(row):
    parts = tuple(norm(row.get(key)) for key in FIELDS)
    return parts if all(parts) else None

def bounded_pairs(groups):
    total = sum(len(g) * (len(g) - 1) // 2 for g in groups.values())
    require(total <= MAX_PAIRS, "candidate pair bound exceeded")
    for group in groups.values():
        yield from itertools.combinations(group, 2)

def audit(packs):
    names = sorted(packs)
    ccns, addresses = defaultdict(list), defaultdict(list)
    source_counts = {}
    for source in names:
        pack = packs[source]
        require(pack["source"] == source and pack["row_count"] == len(pack["records"]), "source membership mismatch")
        seen = set()
        missing_address = 0
        for row in pack["records"]:
            ccn = row.get("ccn")
            require(isinstance(ccn, str) and ccn and ccn == ccn.strip() and ccn not in seen, "missing, unnormalized or duplicate source identifier")
            seen.add(ccn)
            key = (source, ccn)
            addr = complete_address(row)
            item = (key, norm(row.get("state")), addr)
            ccns[ccn].append(item)
            if addr is not None:
                addresses[addr].append(item)
            else:
                missing_address += 1
        source_counts[source] = {"provider_source_records": len(seen), "incomplete_reported_address": missing_address, "same_source_address_groups": 0, "same_source_address_group_records": 0}
    for group in addresses.values():
        counts = Counter(item[0][0] for item in group)
        for source, n in counts.items():
            if n > 1:
                source_counts[source]["same_source_address_groups"] += 1
                source_counts[source]["same_source_address_group_records"] += n

    labels = ("same_ccn_candidates", "same_ccn_same_state", "same_ccn_conflicting_state", "same_ccn_missing_state", "same_ccn_complete_address", "same_ccn_different_complete_address", "same_ccn_incomplete_address", "same_address_pairs", "same_address_distinct_ccn")
    pairs = {p: Counter({k: 0 for k in labels}) for p in itertools.combinations(names, 2)}
    members = {p: (set(), set()) for p in pairs}

    def oriented(a, b):
        if a[0][0] == b[0][0]:
            return None
        if a[0][0] > b[0][0]:
            a, b = b, a
        p = (a[0][0], b[0][0])
        members[p][0].add(a[0])
        members[p][1].add(b[0])
        return p, a, b

    for a, b in bounded_pairs(ccns):
        pair = oriented(a, b)
        if pair is None:
            continue
        p, a, b = pair
        c = pairs[p]
        c["same_ccn_candidates"] += 1
        state = "missing_state" if not a[1] or not b[1] else "same_state" if a[1] == b[1] else "conflicting_state"
        c["same_ccn_" + state] += 1
        address = "incomplete_address" if a[2] is None or b[2] is None else "complete_address" if a[2] == b[2] else "different_complete_address"
        c["same_ccn_" + address] += 1

    for a, b in bounded_pairs(addresses):
        pair = oriented(a, b)
        if pair is None:
            continue
        p, a, b = pair
        c = pairs[p]
        c["same_address_pairs"] += 1
        if a[0][1] != b[0][1]:
            c["same_address_distinct_ccn"] += 1

    result = []
    for (left, right), counts in pairs.items():
        require(counts["same_ccn_candidates"] == sum(counts["same_ccn_" + k] for k in ("same_state", "conflicting_state", "missing_state")), "state grain reconciliation")
        require(counts["same_ccn_candidates"] == sum(counts["same_ccn_" + k] for k in ("complete_address", "different_complete_address", "incomplete_address")), "address grain reconciliation")
        require(counts["same_address_pairs"] == counts["same_address_distinct_ccn"] + counts["same_ccn_complete_address"], "overlap reconciliation")
        left_members, right_members = members[(left, right)]
        result.append({"left_source": left, "right_source": right, **dict(counts), "left_records_with_candidate": len(left_members), "right_records_with_candidate": len(right_members), "union_candidate_pairs": counts["same_ccn_candidates"] + counts["same_address_distinct_ccn"]})
    return {"scope": "Exact source-scoped cross-program identifier/address candidate counts; not physical sites, canonical identities, active status, ownership or campus relationships. Only case and whitespace normalized; no fuzzy names, abbreviations, ZIP truncation or geocoding. Counts are pairs, not unique facilities.", "provider_source_records": sum(x["provider_source_records"] for x in source_counts.values()), "sources": source_counts, "source_pairs": result, "canonical_merges": 0}

def load(root):
    summary = json.loads((root / "web/market-summary.json").read_text())
    packs, pins = {}, {}
    for key, pin in sorted(summary["sources"].items()):
        require(key in ("hospital", "nursing", "dialysis", "home-health", "hospice", "rehabilitation", "long-term-hospital"), "unqualified source")
        path = root / "web/public-directory" / (key + ".json")
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == pin["sha256"], "directory SHA-256 mismatch: " + key)
        pack = json.loads(raw)
        require(pack["row_count"] == pin["rows"] and pack["release"] == pin["release"], "directory release/count mismatch")
        packs[key] = pack
        pins[key] = pin
    require(len(packs) == 7 and sum(p["rows"] for p in pins.values()) == summary["provider_rows"], "market directory scope mismatch")
    return packs, pins

def qualified(root=ROOT):
    packs, pins = load(root)
    return {**audit(packs), "source_pins": pins}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = qualified()
    if args.output:
        with args.output.open("x") as out:
            json.dump(result, out, indent=2, sort_keys=True)
    print("FACILITYSIGNAL_PUBLIC_IDENTITY_AUDIT", json.dumps(result, sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
