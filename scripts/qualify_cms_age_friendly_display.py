"""Qualify the six displayed national Age Friendly Hospital attestation categories."""
import re

RELEASE="2026-11-12"
PERIOD=("01/01/2025","12/31/2025")
DOMAIN={f"AFH_S{i}_N_RATE":i for i in range(6)}

def qualify(rows,release):
    if release!=RELEASE or len(rows)!=6 or {r[0] for r in rows}!=set(DOMAIN):
        raise ValueError("Unexpected release or incomplete national distribution")
    vals={}
    for mid,label,kind,metric,raw,annotation,start,end in rows:
        category=DOMAIN[mid]
        if (start,end)!=PERIOD or kind!="Hospital Measure" or metric!="Age Friendly Hospital Measure":
            raise ValueError("Unexpected measure or period")
        if annotation or not re.fullmatch(r"[0-9]{1,3}",raw) or int(raw)>100:
            raise ValueError("Unexpected displayed numeric or annotation domain")
        if not label.startswith(f"Hospitals Scoring {category} out of 5 points"):
            raise ValueError("Measure label conflicts with score category")
        vals[str(category)]=int(raw)
    return {"national_display_categories_verified":len(vals),"displayed_scores_by_attestation_category":vals,
            "sum_of_displayed_scores":sum(vals.values()),"reporting_denominator":None,
            "facility_attestations_or_links_emitted":0,"outcome_or_certification_inferences":0}
