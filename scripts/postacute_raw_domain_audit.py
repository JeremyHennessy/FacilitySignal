"""Exact pinned postacute directory audit; aggregate outputs, no new public rows."""
import argparse
from collections import Counter
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
import tempfile

import qualified_data_use as q
from restore_snapshot import fetch_missing, verify_raw

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("hospice", "long-term-hospital", "rehabilitation")
REGIONS = {
    1: "CT ME MA NH RI VT",
    2: "NJ NY PR VI",
    3: "DE DC MD PA VA WV",
    4: "AL FL GA KY MS NC SC TN",
    5: "IL IN MI MN OH WI",
    6: "AR LA NM OK TX",
    7: "IA KS MO NE",
    8: "CO MT ND SD UT WY",
    9: "AZ CA HI NV AS GU MP",
    10: "AK ID OR WA",
}
STATE_REGION = {state: region for region, group in REGIONS.items() for state in group.split()}
REGION_REFERENCE = "https://www.cms.gov/medicare-coverage-database/help/all-page-help-text.aspx"
DATE = re.compile(r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}\Z")
CCN = re.compile(r"[A-Z0-9]{6}\Z")
ZIP = re.compile(r"[0-9]{5}(?:-[0-9]{4})?\Z")
MARKERS = {"": "blank", "-": "dash", "not available": "not_available",
           "not applicable": "not_applicable", "n/a": "n_a", "unknown": "unknown"}

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def marker(value):
    return MARKERS.get(value.strip().casefold())

def owner(value, labels):
    v=value.strip()
    m=marker(v)
    if m:
        return m, None
    lookup={x.casefold():x for x in labels}
    if v in labels:
        return "exact_trimmed",v
    if v.casefold() in lookup:
        return "casefold_match",lookup[v.casefold()]
    # Only explicitly recognized punctuation variants are candidate mappings.
    # Never expose an arbitrary unexpected string or silently promote an alias.
    norm=lambda s: " ".join(s.casefold().replace("-"," ").split())
    candidates=[x for x in labels if norm(x)==norm(v)]
    if len(candidates)==1:
        return "punctuation_candidate",candidates[0]
    return "unmapped",None

def cert_date(v, release):
    m=marker(v)
    if m:
        return m
    v=v.strip()
    if not DATE.fullmatch(v):
        return "syntax_review"
    try:
        d=datetime.strptime(v,"%m/%d/%Y").date()
    except ValueError:
        return "calendar_review"
    return "after_release" if d>release else "valid_calendar_date"

def region_state(state, region):
    s=state.strip().upper()
    v=region.strip()
    if s not in STATE_REGION:
        return "unknown_jurisdiction"
    if v not in {str(n) for n in REGIONS}:
        return "region_value_review"
    return "matches_reference" if int(v)==STATE_REGION[s] else "region_mismatch"

def audit_rows(rows, spec, pin, shard):
    q.compare_directory(shard,pin,rows)
    labels=spec["fields"][10]["documented_domain"]
    q.need(len(labels)==len({x.casefold() for x in labels}),"ownership dictionary ambiguity")
    owner_states, owners, aliases, dates, regions, region_counts = [Counter() for _ in range(6)]
    secondary, telephone, ccn_shapes, zip_shapes, beds = [Counter() for _ in range(5)]
    unknown_owner=set()
    values=[]
    release=date.fromisoformat(pin["release"])
    public={ (r["ccn"],r["state"]):r for r in shard["records"] }
    for key,(row,_) in rows.items():
        state,label=owner(row["Ownership Type"],labels)
        owner_states[state]+=1
        if state=="unmapped":
            unknown_owner.add(row["Ownership Type"].strip())
            q.need(len(unknown_owner)<=64,"ownership domain unexpectedly large")
        elif state=="punctuation_candidate":
            aliases[label]+=1
        elif label:
            owners[label]+=1
        dates[cert_date(row["Certification Date"],release)]+=1
        region=region_state(row["State"],row["CMS Region"])
        regions[region]+=1
        if row["CMS Region"].strip() in {str(n) for n in REGIONS}:
            region_counts[row["CMS Region"].strip()]+=1
        secondary[marker(row["Address Line 2"]) or "reported_nonblank"]+=1
        telephone["nonblank" if row["Telephone Number"].strip() else "blank"]+=1
        ccn_shapes["six_alphanumeric" if CCN.fullmatch(row["CMS Certification Number (CCN)"].strip()) else "review"]+=1
        zip_shapes["postal_shape" if ZIP.fullmatch(row["ZIP Code"].strip()) else "review"]+=1
        if pin["key"]=="long-term-hospital":
            v,kind=q.quantity(row["Total Number of Beds"])
            beds[kind]+=1
            q.need(public[key]["capacity"]==v,"existing public bed projection differs")
            if kind=="reported_integer":
                values.append(int(v))
    n=len(rows)
    for c in (owner_states,dates,regions,secondary,telephone,ccn_shapes,zip_shapes):
        q.need(sum(c.values())==n,"aggregate rows do not reconcile")
    q.need(sum(owners.values())==owner_states["exact_trimmed"]+owner_states["casefold_match"],"ownership counts do not reconcile")
    q.need(sum(aliases.values())==owner_states["punctuation_candidate"],"ownership alias counts do not reconcile")
    result={"source":pin["key"],"source_sha256":pin["sha256"],"release":pin["release"],"rows":n,
            "headers":len(spec["fields"]),"identity_projection_parity":n,"ownership_states":dict(owner_states),
            "ownership_qualified_categories":dict(owners),"ownership_punctuation_candidates":dict(aliases),
            "ownership_unmapped_distinct":len(unknown_owner),"certification_dates":dict(dates),
            "region_states":dict(regions),"region_counts":dict(region_counts),"secondary_address":dict(secondary),
            "telephone_presence_only":dict(telephone),"ccn_shapes":dict(ccn_shapes),"zip_shapes":dict(zip_shapes)}
    if pin["key"]=="long-term-hospital":
        q.need(sum(beds.values())==n and len(values)==beds["reported_integer"],"bed counts")
        result["beds"]={"states":dict(beds),"reported":len(values),"sum":sum(values),
                        "min":min(values) if values else None,"max":max(values) if values else None,
                        "zero":values.count(0),"existing_projection_parity":n}
    return result

def hha_reconciliation(root=ROOT):
    old=read(root/"research/qualified_data_use_20261126.json")["hha"]
    recent=read(root/"research/hha_raw_domain_log_summary_20261126.json")
    pin=next(s for s in read(root/"research/snapshot_release_20261125.json")["sources"] if s["key"]=="home-health")
    q.need(old["source_sha256"]==recent["source_sha256"]==pin["sha256"] and old["release"]==recent["release"]==pin["release"],"HHA pin drift")
    q.need(old["rows"]==recent["observations"]["rows"]==pin["stored_rows"],"HHA row drift")
    owners=old["ownership"]
    expected=set(q.OWNERSHIP.values())
    q.need(set(owners)==expected|{"other_or_missing"},"HHA category drift")
    nonmissing=sum(owners[k] for k in expected)
    raw=recent["observations"]["ownership"]
    q.need(nonmissing==raw["unmapped_category"] and recent["observations"]["ownership_unmapped_distinct"]==len(expected),"HHA nonmissing mismatch")
    q.need(old["ownership_other_states"]=={"dash_marker":raw["dash"]} and owners["other_or_missing"]==raw["dash"] and sum(owners.values())==old["rows"],"HHA missing mismatch")
    return {"source_sha256":pin["sha256"],"release":pin["release"],"rows":old["rows"],
            "casefold_qualified_categories":{k:owners[k] for k in sorted(expected)},
            "missing_dash":raw["dash"],"unmapped_after_prior_casefold":0,
            "exact_raw_spelling_retained":False,"new_downloads":0,
            "evidence":"qualified_data_use.py classify strips/casefolds against explicit dictionary labels; both audits exact same source hash. Exact raw spellings not retained."}

def qualify(raw_root=None, root=ROOT):
    specs=read(root/"research/postacute_directory_semantics_20261126.json")
    pins={s["key"]:s for s in read(root/"research/snapshot_release_20261125.json")["sources"]}
    by_source={s["source"]:s for s in specs["sources"]}
    q.need(set(by_source)==set(SOURCES) and len(STATE_REGION)==56,"qualification scope")
    results=[]
    downloads=0
    with tempfile.TemporaryDirectory(prefix="facilitysignal-postacute-domain-") as t:
        for k in SOURCES:
            spec,pin=by_source[k],pins[k]
            q.need(spec["source_sha256"]==pin["sha256"] and spec["release"]==pin["release"] and spec["rows"]==pin["stored_rows"],"semantic pin drift")
            q.need(0<pin["bytes"]<=1_000_000,"publisher size limit")
            path=(raw_root/pin["file"]) if raw_root else Path(t)/pin["file"]
            if raw_root is None:
                fetch_missing(pin,path)
                downloads+=1
            verify_raw(path,pin)
            fields=[f["field"] for f in spec["fields"]]
            rows=q.source_rows(path,pin,fields)
            shard=read(root/"web/public-directory"/(k+".json"))
            result=audit_rows(rows,spec,pin,shard)
            verify_raw(path,pin)
            results.append(result)
    q.need(sum(r["rows"] for r in results)==8003 and sum(r["headers"] for r in results)==37,"scope totals")
    prior=read(root/"research/qualified_data_use_20261126.json")["ltch"]
    b=next(r["beds"] for r in results if r["source"]=="long-term-hospital")
    q.need(all(b[k]==prior[k] for k in ("reported","sum","min","max","zero")) and b["states"]==prior["value_states"],"LTCH retained capacity reconciliation")
    return {"status":"AUDIT_COMPLETE_NOT_PUBLICATION_APPROVAL","sources":results,"hha_reconciliation":hha_reconciliation(root),
            "publisher_downloads":downloads,"publisher_bytes":sum(pins[k]["bytes"] for k in SOURCES) if downloads else 0,
            "region_reference":REGION_REFERENCE,"new_application_approved_fields":0,"new_public_row_fields":0,
            "limits":"Source identity parity only, not canonical matches. Region concordance is an administrative reference, not a service area. Unmapped labels withheld. Initial Medicare dates not proof of active operation."}

def main():
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--download",action="store_true")
    g.add_argument("--raw-dir",type=Path)
    p.add_argument("--receipt",type=Path,required=True)
    a=p.parse_args()
    q.need(not a.receipt.exists(),"receipt exists")
    result=qualify(a.raw_dir)
    with a.receipt.open("x",encoding="utf-8") as out:
        json.dump(result,out,indent=2,sort_keys=True)
    print("POSTACUTE_RAW_DOMAIN",json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
