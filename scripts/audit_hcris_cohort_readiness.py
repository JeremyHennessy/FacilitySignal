"""Reconcile pinned aggregate HCRIS evidence; never open row-level data or Azure."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "research"
FILES = (
    "hcris_direct_measure_crosswalk_20261126.json",
    "hcris_three_way_candidates_20261126.json",
    "hcris_capacity_candidate_receipts_20261126.json",
    "azure_archive_inventory_20261126.json",
)

def require(condition, reason):
    if not condition:
        raise ValueError(reason)

def overlap_bounds(universe, cohort, positive):
    """Cardinality bounds, not an observed intersection."""
    require(all(type(x) is int for x in (universe, cohort, positive))
            and 0 <= cohort <= universe and 0 <= positive <= universe,
            "invalid cohort counts")
    return max(0, cohort + positive - universe), min(cohort, positive)

def audit(direct, three, capacity, archive):
    result = {}
    for form in ("hospital", "snf"):
        d, t, c = (x["forms"][form] for x in (direct, three, capacity))
        n, k = d["report_key_intersection"], c["candidate_reports"]
        require(d["archive_source_sha256"] == t["publisher_archive_sha256"] == c["archive_sha256"]
                and d["puf_sha256"] == t["puf_sha256"] == c["source_sha256"],
                "release checksum mismatch")
        require(n == t["report_key_intersection"]
                and k == t["nonconflicting_three_way_candidate_reports"]
                == t["candidate_states"]["three_way_candidate"]
                and sum(t["candidate_states"].values()) == n
                and c["candidate_providers"] == t["candidate_provider_records"]
                and c["directory"] == t["directory"], "cohort metadata mismatch")
        require(d["archive_reports"] == n + d["archive_only_report_keys"]
                and d["puf_reports"] == n + d["puf_only_report_keys"], "report counts")
        require(not d["monetary_scale_qualified"] and not t["monetary_scale_qualified"]
                and not t["publication_cleared"] and not c["public_promotion"]
                and not c["row_level_output_retained"], "review boundary changed")
        receipt = [x for x in archive["receipts"] if x["key"] == f"hcris-{form}-2024-index"]
        require(len(receipt) == 1 and receipt[0]["observations"] == d["archive_reports"]
                and receipt[0]["source_sha256"] == d["archive_source_sha256"], "archive index mismatch")
        shards = [x for x in archive["receipts"] if x["key"].startswith(f"hcris-{form}-2024-numeric-")]
        require(len(shards) == len({x["key"] for x in shards}) == d["numeric_shards"]
                and sum(x["observations"] for x in shards) == d["verified_archived_numeric_rows"],
                "archive numeric shard mismatch")
        measures = {}
        for name, m in sorted(d["measures"].items()):
            counts = m["comparisons"]
            require(set(counts) == {"equal_decimal", "puf_missing_archive_absent"}
                    and sum(counts.values()) == n
                    and m["qualification"] == "matched_report_parity_supported",
                    "measure parity not established")
            eq = counts["equal_decimal"]
            lo, hi = overlap_bounds(n, k, eq)
            measures[name] = {"equal_in_intersection": eq, "missing_in_intersection": counts["puf_missing_archive_absent"],
                              "minimum_candidate_equal": lo, "maximum_candidate_equal": hi,
                              "unit_candidate": m["unit_candidate"]}
        result[form] = {"intersection": n, "candidates": k,
                        "numeric_rows": d["verified_archived_numeric_rows"], "measures": measures}
    return {"scope": "Conditional cardinality bounds on the same pinned report-key intersection; no row-level join or financial attribution",
            "public_promotion": False, "monetary_scale_qualified": False, "forms": result}

def load_inputs(root=ROOT):
    return [json.loads((root / f).read_text(encoding="utf-8")) for f in FILES]

if __name__ == "__main__":
    print(json.dumps(audit(*load_inputs()), indent=2, sort_keys=True))
