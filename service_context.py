"""Aggregate source-category research context; no facility-level leads or risk scores."""
import argparse
import json
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path

from build_combined import require, readonly, sha, validate_base
from citation_evidence import BASE_SHA, EXPECTED, domain, date_state
from citation_dictionary import RELEASE, norm, status_bucket

# Exact publisher category text only; no tag number or keyword-based asset inference.
HEALTH_CONTEXT = {
    "infection control deficiencies": "infection_prevention_context",
    "nutrition and dietary deficiencies": "food_service_context",
}

def context(dataset, tag, category):
    scope = domain(dataset, tag)
    if scope == "life_safety_source":
        return "broad_life_safety_context"
    if scope == "emergency_preparedness_source":
        return "broad_preparedness_context"
    if scope == "health_context_only":
        return HEALTH_CONTEXT.get(norm(category), "other_health_context")
    return "unresolved_domain"

def audit(db, expected):
    result = {}
    for dataset, expected_rows in expected.items():
        row = db.execute("SELECT r.id,r.published_on FROM current_release c JOIN releases r ON r.id=c.release_id AND r.dataset=c.dataset WHERE c.dataset=?", (dataset,)).fetchone()
        require(row is not None and row[1] == RELEASE, "citation release mismatch")
        rid, published = row
        release = date.fromisoformat(published)
        contexts, statuses, dates = Counter(), Counter(), Counter()
        n = 0
        for tag, category, status, survey, correction, row_release in db.execute(
            "SELECT tag,category,correction_status,survey_date,correction_date,release_id FROM findings WHERE dataset=?", (dataset,)
        ):
            require(row_release == rid, "citation lineage mismatch")
            contexts[context(dataset, tag, category)] += 1
            statuses[status_bucket(status)] += 1
            dates[date_state(survey, release) + "/" + date_state(correction, release)] += 1
            n += 1
        require(n == expected_rows == sum(contexts.values()) == sum(statuses.values()) == sum(dates.values()), "context reconciliation")
        result[dataset] = {"rows": n, "research_context_counts": dict(contexts),
                           "literal_status_counts": dict(statuses), "date_state_counts": dict(dates)}
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cms-base", type=Path, required=True)
    p.add_argument("--audit", type=Path, required=True)
    a = p.parse_args()
    require(not a.audit.exists(), "audit already exists")
    path = a.cms_base / "facilitysignal.sqlite3"
    require(sha(path) == BASE_SHA, "retained baseline checksum mismatch")
    validate_base(a.cms_base)
    with closing(readonly(path)) as db:
        result = audit(db, EXPECTED)
    require(sha(path) == BASE_SHA, "source mutated")
    report = {"version":"service-context-v1", "source_database_sha256":BASE_SHA,
              "source_artifact_id":15046953633, "citation_rows":sum(EXPECTED.values()),
              "sources":result, "confirmed_opportunities":0,
              "limits":"National aggregate research contexts only; no individual identifiers, category/status raw text, cross-tab of context with status, equipment, risk, purchasing need, or current deficiency inference. Broad F categories include clinical activities; no claim of outsourced service demand. Tag-version and dispute flags are unavailable. No row-level redistribution."}
    a.audit.parent.mkdir(parents=True, exist_ok=True)
    with a.audit.open("x") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print("SERVICE_CONTEXT_AUDIT", json.dumps(report, sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
