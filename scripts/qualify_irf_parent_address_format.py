"""Aggregate-only IRF address text sensitivity audit on previously pinned projections.
No canonical linking, address geocoding, ownership, or site assertions.
"""
import json
import re
import unicodedata
from collections import defaultdict
from scripts import qualify_irf_parent_candidates as parent

def text_key(value):
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFKC", value).upper())

def format_equal(a, b, fields):
    return all(text_key(a.get(k)) and text_key(a.get(k)) == text_key(b.get(k)) for k in fields)

def audit_rows(irf, parents):
    index = defaultdict(list)
    for row in parents:
        index[row["ccn"]].append(row)
    result = {}
    seen = set()
    for row in irf:
        token = row["ccn"]
        if token in seen:
            raise ValueError("duplicate IRF identifier")
        seen.add(token)
        kind, key = parent.candidate(token)
        if key is None:
            continue
        shape = "extended" if kind.startswith("extended_") else kind
        counts = result.setdefault(shape, dict.fromkeys(
            ("total", "exact_address_context", "format_only_address_context",
             "different_context", "multiple", "missing_or_conflict"), 0))
        counts["total"] += 1
        matches = [p for p in index.get(key, []) if parent.equal(p, row, ("state",))]
        if len(matches) > 1:
            status = "multiple"
        elif not matches:
            status = "missing_or_conflict"
        elif parent.equal(matches[0], row, parent.FIELDS):
            status = "exact_address_context"
        elif (format_equal(matches[0], row, ("address", "city"))
              and parent.equal(matches[0], row, ("zip",))):
            status = "format_only_address_context"
        else:
            status = "different_context"
        counts[status] += 1
    for counts in result.values():
        if counts["total"] != sum(v for k, v in counts.items() if k != "total"):
            raise ValueError("unreconciled candidates")
    return result

def audit():
    return audit_rows(parent.load("rehabilitation"),
                      parent.load("hospital") + parent.load("long-term-hospital"))

if __name__ == "__main__":
    print(json.dumps(audit(), sort_keys=True))
