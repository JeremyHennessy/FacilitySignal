"""Read-only aggregate field profiler for the nine committed public shards.

Uses full local files, not truncated remote connector responses. Never outputs
provider names, identifiers, addresses, ZIP values or raw row contents.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_FIELDS = {"ccn", "name", "address", "city", "state", "zip", "capacity"}
CITATION_FIELDS = {"ccn", "state", "name", "citation_rows"}
SOURCES = {"hospital", "nursing", "dialysis", "home-health", "hospice",
           "rehabilitation", "long-term-hospital", "nursing-health", "nursing-fire"}
UNITS = {"nursing": "certified beds", "dialysis": "dialysis stations"}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, "duplicate JSON key")
        out[key] = value
    return out

def read_json(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid JSON number")))

def profile_field(rows, name, numeric=False):
    counts = Counter()
    values = set()
    numeric_values = []
    for row in rows:
        value = row[name]
        if value is None:
            counts["null"] += 1
            continue
        require(type(value) in (str, int), "unexpected scalar field type")
        if isinstance(value, str) and not value.strip():
            counts["blank"] += 1
            continue
        counts["nonblank"] += 1
        values.add((type(value).__name__, value))
        if numeric:
            if isinstance(value, int) and value >= 0 or (
                isinstance(value, str) and re.fullmatch(r"[0-9]+", value)
            ):
                numeric_values.append(int(value))
            else:
                counts["non_numeric_or_negative"] += 1
    result = {"nonblank": counts["nonblank"], "blank": counts["blank"],
              "null": counts["null"], "distinct_nonblank": len(values)}
    require(sum(result[k] for k in ("nonblank", "blank", "null")) == len(rows),
            "field count reconciliation failed")
    if numeric:
        result.update(numeric_nonnegative_integer_rows=len(numeric_values),
                      non_numeric_or_negative=counts["non_numeric_or_negative"],
                      zero_rows=sum(n == 0 for n in numeric_values),
                      min=min(numeric_values) if numeric_values else None,
                      max=max(numeric_values) if numeric_values else None,
                      sum=sum(numeric_values) if numeric_values else None)
        require(len(numeric_values)+counts["non_numeric_or_negative"] == counts["nonblank"],
                "numeric count reconciliation failed")
    return result

def profile_shard(path, source, expected, release, jurisdictions):
    obj = read_json(path)
    citation = source in {"nursing-health", "nursing-fire"}
    columns = CITATION_FIELDS if citation else PROVIDER_FIELDS
    require(obj["source"] == source and obj["release"] == release, "release/source mismatch")
    rows = obj["records"]
    require(isinstance(rows, list) and len(rows) == expected["published_records"],
            "published count mismatch")
    require(all(isinstance(row, dict) and set(row) == columns for row in rows),
            "unexpected projection schema")
    for row in rows:
        for key in columns - {"citation_rows"}:
            require(isinstance(row[key], str), "expected string in public projection")
        require(re.fullmatch(r"[A-Z0-9]{6}", row["ccn"]) is not None, "invalid projected CCN")
        require(row["state"] in jurisdictions, "unexpected jurisdiction")
        if citation:
            require(type(row["citation_rows"]) is int and row["citation_rows"] > 0,
                    "invalid citation aggregate")
    keys = {(r["ccn"], r["state"]) for r in rows}
    require(len(keys) == len(rows), "duplicate projected CCN/state key")
    stats = {name: profile_field(rows, name, name in {"capacity", "citation_rows"})
             for name in sorted(columns)}
    n = stats["citation_rows"]["sum"] if citation else len(rows)
    require(n == obj["row_count"] == expected["source_rows"], "source count mismatch")
    result = {"source": source, "release": release,
              "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "published_rows": len(rows), "source_rows": n, "columns": stats,
              "distinct_ccn_state": len(keys),
              "capacity_unit": None if citation else UNITS.get(source),
              "capacity_note": "Published capacity values are not installed equipment or occupancy."}
    if not citation:
        valid = [r for r in rows if all(r[k].strip() for k in ("address", "city", "state", "zip"))]
        addresses = {tuple(" ".join(r[k].upper().split()) for k in ("address", "city", "state", "zip"))
                     for r in valid}
        result["complete_reported_address_rows"] = len(valid)
        result["distinct_reported_address_tuples"] = len(addresses)
    return result

def build(root=ROOT):
    directory = root / "web/public-directory"
    manifest = read_json(directory / "manifest.json")
    lock = read_json(root / "research/snapshot_release_20261125.json")
    expected = manifest["sources"]
    require(set(expected) == SOURCES, "unexpected source set")
    releases = {s["key"]: s for s in lock["sources"] if s["family"] == "care-compare"}
    require(set(releases) == SOURCES, "release-lock scope mismatch")
    require(set(p.stem for p in directory.glob("*.json")) == SOURCES | {"manifest"},
            "directory file set mismatch")
    results = []
    for source in sorted(SOURCES):
        entry = releases[source]
        require(entry["stored_rows"] == expected[source]["source_rows"], "lock/manifest count mismatch")
        results.append(profile_shard(directory / (source + ".json"), source, expected[source],
                                     entry["release"], set(manifest["jurisdictions"])))
    providers = sum(x["source_rows"] for x in results if x["source"] not in {"nursing-health", "nursing-fire"})
    citations = sum(x["source_rows"] for x in results if x["source"] in {"nursing-health", "nursing-fire"})
    require(providers == manifest["provider_rows"], "provider totals mismatch")
    require(citations == manifest["citation_source_rows"], "citation totals mismatch")
    return {"format_version": 1, "scope": "Full committed public projection only; no raw publisher fields or current compliance conclusions.",
            "manifest_sha256": hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest(),
            "release_lock_sha256": hashlib.sha256((root / "research/snapshot_release_20261125.json").read_bytes()).hexdigest(),
            "sources_profiled": len(results), "provider_rows": providers,
            "citation_source_rows": citations,
            "published_rows": sum(x["published_rows"] for x in results), "sources": results}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, help="Optional new aggregate JSON; refuses overwrite.")
    a = p.parse_args()
    result = build()
    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if a.output:
        with a.output.open("x", encoding="utf-8") as f:
            f.write(content)
    else:
        print(content, end="")

if __name__ == "__main__":
    main()
