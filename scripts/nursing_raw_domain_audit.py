"""Aggregate-only audit of exact pinned nursing directory, no row-level outputs."""
import argparse
from collections import Counter
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import re
import tempfile
import qualified_data_use as q
from restore_snapshot import fetch_missing, verify_raw

ROOT=Path(__file__).resolve().parents[1]
NUMBER=re.compile(r"[+-]?[0-9]{1,12}(?:\.[0-9]{1,12})?\Z")
ISO_DATE=re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
CODE_SEQUENCE=re.compile(r"[0-9]{1,2}(?:[ ,;]+[0-9]{1,2})*\Z")
KNOWN_CODES={1,2,6,7,9,10,13,14,18,20,21,22,23,24,25,26,27,28,29}
OWNERS={
    "for profit - individual":"for_profit_individual",
    "for profit - partnership":"for_profit_partnership",
    "for profit - corporation":"for_profit_corporation",
    "for profit - limited liability company":"for_profit_llc_company_label",
    "for profit - limited liability corporation":"for_profit_llc_corporation_label",
    "non profit - church related":"nonprofit_church",
    "non profit - corporation":"nonprofit_corporation",
    "non profit - other":"nonprofit_other",
    "government - state":"government_state",
    "government - county":"government_county",
    "government - city":"government_city",
    "government - city/county":"government_city_county",
    "government - hospital district":"government_hospital_district",
    "government - federal":"government_federal",
}
PROVIDERS={"medicare":"medicare","medicaid":"medicaid","medicare and medicaid":"medicare_and_medicaid"}

def category(v,domain):
    x=v.strip().casefold()
    if x in q.MARKERS:return q.MARKERS[x]
    return domain.get(x,"unmapped")

def decimal_value(v,nonnegative=True,integer=False):
    v=v.strip()
    if v.casefold() in q.MARKERS:return q.MARKERS[v.casefold()],None
    if not NUMBER.fullmatch(v):return "syntax_review",None
    n=Decimal(v)
    if (nonnegative and n<0) or (integer and n!=n.to_integral_value()):
        return "domain_review",None
    return "reported",n

def date_state(v,release):
    v=v.strip()
    if v.casefold() in q.MARKERS:return q.MARKERS[v.casefold()]
    if not ISO_DATE.fullmatch(v):return "syntax_review"
    try:d=date.fromisoformat(v)
    except ValueError:return "calendar_review"
    return "after_release" if d>release else "calendar_date"

def footnote(v):
    v=v.strip()
    if not v:return "blank"
    if not CODE_SEQUENCE.fullmatch(v):return "syntax_review"
    codes=[int(x) for x in re.findall(r"[0-9]+",v)]
    if any(c not in KNOWN_CODES for c in codes):return "unmapped_numeric_code"
    return "+".join(str(c) for c in codes)

def coordinate_state(lat,lon):
    a,x=decimal_value(lat,False);b,y=decimal_value(lon,False)
    if a!="reported" or b!="reported":return "incomplete_or_syntax_review"
    if not(-90<=x<=90 and -180<=y<=180):return "outside_global_bounds"
    if x==0 and y==0:return "zero_pair_review"
    if x==0 or y==0:return "one_zero_review"
    return "within_global_bounds"

def audit_rows(rows,pin,shard,fields):
    q.compare_directory(shard,pin,rows)
    release=date.fromisoformat(pin["release"])
    owners,provider,urban,hospital,ccrc,dates,processed,beds,census,pairs,geo,geo_joint=[Counter() for _ in range(12)]
    owner_unknown=set(); provider_unknown=set()
    note_fields=[f["field"] for f in fields if f["kind"]=="footnote"]
    q.need(len(note_fields)==15,"footnote header coverage")
    notes={f:Counter() for f in note_fields}
    bed_values=[];resident_values=[];paired_beds=Decimal(0);paired_residents=Decimal(0)
    public={(r["ccn"],r["state"]):r for r in shard["records"]}
    for k,(row,_) in rows.items():
        o=category(row["Ownership Type"],OWNERS)
        owners[o]+=1
        if o=="unmapped":
            owner_unknown.add(row["Ownership Type"].strip())
            q.need(len(owner_unknown)<=32,"unexpected ownership cardinality")
        p=category(row["Provider Type"],PROVIDERS)
        provider[p]+=1
        if p=="unmapped":
            provider_unknown.add(row["Provider Type"].strip())
            q.need(len(provider_unknown)<=16,"unexpected provider cardinality")
        yn={"y":"reported_yes","n":"reported_no","yes":"reported_yes","no":"reported_no"}
        urban[category(row["Urban"],yn)]+=1
        hospital[category(row["Provider Resides in Hospital"],yn)]+=1
        ccrc[category(row["Continuing Care Retirement Community"],yn)]+=1
        dates[date_state(row["Date First Approved to Provide Medicare and Medicaid Services"],release)]+=1
        processed[date_state(row["Processing Date"],release)]+=1
        bs,b=decimal_value(row["Number of Certified Beds"],integer=True)
        cs,c=decimal_value(row["Average Number of Residents per Day"])
        beds[bs]+=1;census[cs]+=1
        # Capacity is already public. No new per-facility values are retained.
        public_capacity=public[k]["capacity"]
        q.need(public_capacity==("" if b is None else str(int(b))),"published certified bed value differs")
        if b is not None:bed_values.append(int(b))
        if c is not None:resident_values.append(c)
        if b is not None and c is not None:
            pairs["both_reported"]+=1
            pairs["census_above_certified_beds" if c>b else "census_at_or_below_certified_beds"]+=1
            paired_beds+=b;paired_residents+=c
        else:pairs["beds_only" if b is not None else "census_only" if c is not None else "neither_reported"]+=1
        for f in note_fields:notes[f][footnote(row[f])]+=1
        g=coordinate_state(row["Latitude"],row["Longitude"])
        geo[g]+=1
        geo_joint[g+" | "+footnote(row["Geocoding Footnote"])]+=1
    n=len(rows)
    for tally in (owners,provider,urban,hospital,ccrc,dates,processed,beds,census,geo,geo_joint,*notes.values()):
        q.need(sum(tally.values())==n,"aggregate count mismatch")
    q.need(sum(pairs[x] for x in ("both_reported","beds_only","census_only","neither_reported"))==n,"pair scope")
    q.need(pairs["census_above_certified_beds"]+pairs["census_at_or_below_certified_beds"]==pairs["both_reported"],"pair comparison")
    return {
        "status":"AUDIT_COMPLETE_NOT_PUBLICATION_APPROVAL","source":"nursing","source_sha256":pin["sha256"],
        "release":pin["release"],"rows":n,"field_count":len(fields),"identity_projection_parity":n,
        "ownership_candidate_labels":dict(owners),"ownership_unmapped_distinct":len(owner_unknown),
        "provider_reported_categories":dict(provider),"provider_unmapped_distinct":len(provider_unknown),
        "urban":dict(urban),"hospital_location":dict(hospital),"ccrc":dict(ccrc),
        "initial_approval_date":dict(dates),"processing_date":dict(processed),
        "certified_beds":{"states":dict(beds),"reported":len(bed_values),"sum":sum(bed_values),
                          "min":min(bed_values) if bed_values else None,"max":max(bed_values) if bed_values else None,
                          "zero":bed_values.count(0),"public_projection_parity":n},
        "average_daily_residents":{"states":dict(census),"reported":len(resident_values),"sum":str(sum(resident_values,Decimal(0))),
                                   "zero":resident_values.count(Decimal(0))},
        "census_capacity_pairs":dict(pairs),"paired_totals":{"certified_beds":str(paired_beds),"average_daily_residents":str(paired_residents)},
        "coordinate_shape":dict(geo),"coordinate_geocoding_footnote":dict(geo_joint),
        "footnote_counts":{k:dict(v) for k,v in notes.items()},
        "new_application_approved_fields":0,"new_public_row_fields":0,
        "limits":["Ownership labels are comparison candidates based on documented historical category names, not legal title or current-version equivalence.",
                  "Bed/census comparisons are diagnostics between different measures and possible time windows, not validated occupancy.",
                  "Global coordinate bounds and geocoding codes do not establish address accuracy. No coordinates or facility identifiers emitted.",
                  "Footnote code 29 meaning remains October text-only; no individual survey or risk inference. No suppressed values reconstructed."]
    }

def qualify(path,root=ROOT):
    pin=next(s for s in q.read(root/"research/snapshot_release_20261125.json")["sources"] if s["key"]=="nursing")
    sem=q.read(root/"research/nursing_column_semantics_20261127.json")
    prior=next(s for s in q.read(root/"research/public_projection_field_profile_full_20261126.json")["sources"] if s["source"]=="nursing")
    q.need(pin["sha256"]==sem["source_sha256"] and pin["release"]==sem["release"] and pin["stored_rows"]==14686 and 0<pin["bytes"]<=10_000_000,"pinned scope drift")
    fields=sem["fields"];q.need(len(fields)==102,"header scope drift")
    shard_path=root/"web/public-directory/nursing.json"
    q.need(q.sha(shard_path)==prior["file_sha256"],"existing directory hash mismatch")
    verify_raw(path,pin)
    rows=q.source_rows(path,pin,[f["field"] for f in fields])
    result=audit_rows(rows,pin,q.read(shard_path),fields)
    b=result["certified_beds"];p=prior["columns"]["capacity"]
    q.need((b["reported"],b["sum"],b["min"],b["max"],b["zero"])==(p["numeric_nonnegative_integer_rows"],p["sum"],p["min"],p["max"],p["zero_rows"]),"prior capacity mismatch")
    verify_raw(path,pin)
    return result

def main():
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--download",action="store_true")
    g.add_argument("--source",type=Path)
    p.add_argument("--receipt",type=Path,required=True)
    a=p.parse_args()
    q.need(not a.receipt.exists(),"receipt exists")
    pin=next(s for s in q.read(ROOT/"research/snapshot_release_20261125.json")["sources"] if s["key"]=="nursing")
    q.need(0<pin["bytes"]<=10_000_000,"publisher size bound")
    with tempfile.TemporaryDirectory(prefix="facilitysignal-nursing-domain-") as tmp:
        path=a.source or Path(tmp)/"nursing.csv"
        if a.download:fetch_missing(pin,path)
        result=qualify(path)
    result["publisher_downloads"]=int(a.download)
    result["publisher_bytes"]=pin["bytes"] if a.download else 0
    with a.receipt.open("x",encoding="utf-8") as out:json.dump(result,out,indent=2,sort_keys=True)
    print("NURSING_DOMAIN_AUDIT",json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":main()
