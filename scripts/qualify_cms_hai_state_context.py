"""Validate displayed CMS state HAI screening intervals without provider attribution."""
from collections import Counter
import re
from scripts.qualify_cms_hai_benchmark import GROUPS,period,score

KINDS=("CILOWER","CIUPPER","SIR")
REQUIRED={f"HAI_{i}_{t}" for i in range(1,7) for t in KINDS}
RELEASE="2026-11-12"
EDITION_PERIOD=("2025-01-01","2025-12-31")
STATE=re.compile(r"[A-Z]{2}")

def complete_state_context(rows, release):
    if release!=RELEASE:
        raise ValueError("Unsupported state catalog edition")
    if len(rows)!=18 or {r["Measure ID"] for r in rows}!=REQUIRED:
        raise ValueError("A complete one-state benchmark screen must contain 18 distinct fields")
    jurisdiction=rows[0]["State"]
    if not STATE.fullmatch(jurisdiction):
        raise ValueError("Malformed jurisdiction")
    by_id={}
    for row in rows:
        if row["State"]!=jurisdiction or period(row["Start Date"],row["End Date"])!=EDITION_PERIOD:
            raise ValueError("Mixed state or edition period")
        by_id[row["Measure ID"]]=score(row["Score"])
    out={}
    for group in GROUPS:
        prefix=group.removesuffix("SIR")
        values=[by_id[prefix+t] for t in ("CILOWER","SIR","CIUPPER")]
        if any(v is None for v in values):
            out[group]=(jurisdiction,"not_fully_reported")
        elif not values[0]<=values[1]<=values[2]:
            raise ValueError("Point outside its reported interval")
        else:
            out[group]=(jurisdiction,"numeric_ordered_state_interval")
    return out

def provider_state_verdict(provider, state_context):
    """Report availability of aggregate context only; never apply it to the CMS label."""
    group=provider["Measure ID"]
    if group not in GROUPS:
        return "not_sir"
    if provider["Release"]!=RELEASE or period(provider["Start Date"],provider["End Date"])!=EDITION_PERIOD:
        return "different_release_or_period"
    if group not in state_context:
        return "missing_context"
    jurisdiction,status=state_context[group]
    if provider["State"]!=jurisdiction:
        return "different_jurisdiction"
    if score(provider["Score"]) is None:
        return "provider_score_unavailable"
    if status!="numeric_ordered_state_interval":
        return "not_fully_reported"
    return "same_jurisdiction_context_only"

def summarize(rows,providers,state_release):
    context=complete_state_context(rows,state_release)
    return {"state_display_rows_read":len(rows),"measure_families_checked":len(context),
            "state_group_checks":dict(Counter(value[1] for value in context.values())),
            "provider_state_context_checks":dict(Counter(provider_state_verdict(r,context) for r in providers)),
            "numeric_recomparisons_or_label_changes":0,"facility_or_jurisdiction_rows_emitted":0}
