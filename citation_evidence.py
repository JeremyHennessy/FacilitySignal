"""Qualify national citation evidence without publishing individual vulnerabilities or leads."""
import argparse
import json
import re
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path
from build_combined import require, readonly, sha, validate_base

ROOT = Path(__file__).resolve().parent
BASE_SHA = "baa78020a2c60df25408421d4491f66f6f260aa25d3c7579c13199aee9e23960"
DICTIONARY = "https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/nursing_home/NH_Data_Dictionary.pdf"
EXPECTED = {"nursing-fire": 200387, "nursing-health": 418682}
# Match known, source-native text exactly after whitespace/case normalization.
# A date or a plan is not proof of independently verified remediation.
CORRECTION = {
    "deficient, provider has date of correction": "source_reports_date_of_correction",
    "deficient, provider has plan of correction": "source_reports_plan",
    "past non-compliance": "source_reports_past_noncompliance",
}
def correction_state(raw):
    key = " ".join(raw.casefold().split())
    return CORRECTION.get(key, "blank" if not key else "unmapped")

def date_state(raw, release):
    if not raw.strip():
        return "blank"
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",raw.strip()):
        return "non_iso_uninterpreted"
    try:
        day = date.fromisoformat(raw.strip())
    except ValueError:
        return "invalid_iso"
    return "after_release" if day > release else "on_or_before_release"

def domain(dataset, tag):
    # The source combines prefix + tag number; old/new tag version was not retained.
    if dataset == "nursing-fire":
        if re.fullmatch(r"K[0-9]{1,4}",tag):
            return "life_safety_source"
        if re.fullmatch(r"E[0-9]{1,4}",tag):
            return "emergency_preparedness_source"
    elif dataset == "nursing-health" and re.fullmatch(r"F[0-9]{1,4}",tag):
        return "health_context_only"
    return "unmapped"

def evidence(dataset, tag, correction, correction_date, survey_date, release, linked):
    scope = domain(dataset,tag)
    resolution = correction_state(correction)
    observed_date = date_state(survey_date,release)
    corrected_date = date_state(correction_date,release)
    linkage = "same_ccn_state_provider_record" if linked else "unresolved_provider_link"
    # Never infer current exposure, contract demand or an installed asset.
    if scope in ("life_safety_source","emergency_preparedness_source"):
        relevance = "broad_service_research_only"
    elif scope == "health_context_only":
        relevance = "context_only"
    else:
        relevance = "unmapped"
    if resolution in ("source_reports_date_of_correction","source_reports_past_noncompliance"):
        review = "historical_context_only"
    elif resolution == "source_reports_plan":
        review = "plan_requires_status_review"
    else:
        review = "status_unknown"
    confidence = "source_linked_as_of_release" if linked and observed_date == "on_or_before_release" and scope != "unmapped" else "limited"
    return {"source_domain":scope,"resolution_state":resolution,"correction_date_state":corrected_date,
            "survey_date_state":observed_date,"provider_linkage":linkage,"commercial_relevance":relevance,
            "evidence_confidence":confidence,"review_state":review,"current_regulatory_risk":"unknown",
            "confirmed_opportunity":False}

def audit(db, expected):
    result={}
    for dataset,n_expected in expected.items():
        release=db.execute("SELECT r.id,r.published_on FROM current_release c JOIN releases r ON r.id=c.release_id WHERE c.dataset=? AND r.dataset=c.dataset",(dataset,)).fetchone()
        require(release is not None,"missing current source")
        release_id,published=release
        day=date.fromisoformat(published)
        counts={};n=0;unknown_status_values=set()
        for tag,status,correction,survey,linked,record_release in db.execute("""
            SELECT d.tag,d.correction_status,d.correction_date,d.survey_date,
                   f.ccn IS NOT NULL,d.release_id
              FROM findings d LEFT JOIN facilities f
                ON f.dataset='nursing' AND f.ccn=d.ccn AND f.state=d.state
             WHERE d.dataset=?""",(dataset,)):
            require(record_release==release_id,"finding release mismatch")
            e=evidence(dataset,tag,status,correction,survey,day,linked)
            if e["resolution_state"]=="unmapped":
                unknown_status_values.add(status)
            require(e.pop("confirmed_opportunity") is False,"unexpected opportunity promotion")
            for field,value in e.items():
                counts.setdefault(field,Counter())[value]+=1
            n+=1
        require(n==n_expected and all(sum(v.values())==n for v in counts.values()),"citation reconciliation")
        result[dataset]={"release":published,"rows":n,"distributions":{k:dict(v) for k,v in counts.items()},
                         "distinct_unmapped_correction_values":len(unknown_status_values),"confirmed_opportunities":0}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cms-base",type=Path,required=True)
    p.add_argument("--audit",type=Path,required=True)
    a=p.parse_args()
    require(not a.audit.exists(),"audit destination exists")
    path=a.cms_base/"facilitysignal.sqlite3"
    require(sha(path)==BASE_SHA,"retained baseline hash mismatch")
    validate_base(a.cms_base)
    lock=json.loads((ROOT/"research/snapshot_release_20261125.json").read_text())
    pins={s["key"]:s for s in lock["sources"] if s["key"] in (*EXPECTED,"nursing") and s["family"]=="care-compare"}
    with closing(readonly(path)) as db:
        for dataset,pin in pins.items():
            row=db.execute("SELECT r.sha256,r.published_on,r.stored_rows FROM current_release c JOIN releases r ON r.id=c.release_id WHERE c.dataset=?",(dataset,)).fetchone()
            require(row==(pin["sha256"],pin["release"],pin["stored_rows"]),"pinned source drift")
        require(len(pins)==3,"source pins missing")
        result=audit(db,EXPECTED)
    require(sha(path)==BASE_SHA,"source mutated")
    report={"version":"citation-evidence-v1","source_database_sha256":BASE_SHA,"source_artifact_id":15046953633,
            "dictionary_url":DICTIONARY,"sources":result,"citation_rows":sum(EXPECTED.values()),
            "limits":["Aggregate-only output. No identifiers, dates, individual findings, specific equipment, locations or customer records.",
                      "Source correction wording, linkage and broad research applicability are separate. No current regulatory risk score, lead ranking, procurement or independently verified resolution.",
                      "Tag version, dispute flags and inspection cycle are not retained in the existing projection. No tag-level or service-specific mapping; source eligibility and commercial reuse remain review gates."]}
    a.audit.parent.mkdir(parents=True,exist_ok=True)
    with a.audit.open("x") as f:
        json.dump(report,f,indent=2);f.write("\n")
    print("CITATION_EVIDENCE_AUDIT",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
