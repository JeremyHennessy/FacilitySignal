"""Read-only national aggregate evidence. No live compliance or opportunity inference."""
import json

def evidence(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    dictionary = data["citation_dictionary_qualified_baseline"]
    service = data["service_context_qualified_baseline"]
    # Explicit allowlist: do not expose arbitrary future ledger entries or source rows.
    def aggregate(entry):
        return {k: entry[k] for k in ("commit", "run", "artifact", "audit", "reuse_review")}
    return {"scope": "historical national aggregate qualification",
            "live_database_verified": False,
            "citation_dictionary": aggregate(dictionary),
            "service_context": aggregate(service),
            "retention_checkpoint": data["retention_checkpoint"],
            "note": "Aggregate historical research evidence, not current compliance, installed equipment, confirmed purchasing need or live database availability."}
