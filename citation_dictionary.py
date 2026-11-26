"""Qualify publisher citation lookup against the retained release, aggregate evidence only."""
import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from datetime import date, datetime, timezone
import collect_cms as cms
from build_combined import require, readonly, sha, validate_base
from citation_evidence import BASE_SHA, EXPECTED, ROOT, correction_state, date_state

IDENT="tagd-9999"
RELEASE="2026-10-28"
ROWS=643
MAX_BYTES=2_000_000
HEADER=["Deficiency Prefix","Deficiency Tag Number","Deficiency Prefix and Number","Deficiency Description","Deficiency Category"]
# Candidate exact literal statuses; not a validated semantic crosswalk.
STATUS_CANDIDATES={
 "deficient, provider has no plan of correction":"candidate_no_plan",
 "deficient, provider has not corrected":"candidate_not_corrected",
 "deficient, provider has no date of correction":"candidate_no_date",
 "deficient, provider has plan of correction, no date of correction":"candidate_plan_no_date",
 "not corrected":"candidate_not_corrected_literal",
 "deficient, provider has no plan of correction and no date of correction":"candidate_no_plan_no_date",
 "deficient, provider has no plan of correction or date of correction":"candidate_no_plan_or_date",
 "deficient, provider has neither plan of correction nor date of correction":"candidate_neither_plan_nor_date",
}

def norm(s):
    return " ".join(s.casefold().split())

def key(prefix,number):
    require(prefix in ("F","K","E") and re.fullmatch(r"[0-9]{1,4}",number),"invalid dictionary key")
    return prefix+number.zfill(4)

def lookup(data,expected):
    reader=csv.DictReader(io.StringIO(data.decode("utf-8-sig"),newline=""),strict=True)
    require(reader.fieldnames==HEADER,"lookup schema changed")
    entries=defaultdict(set);n=0;duplicates=0
    for row in reader:
        require(None not in row and all(v is not None for v in row.values()),"malformed dictionary row")
        p,num,combined,description,category=(row[h].strip() for h in HEADER)
        k=key(p,num)
        require(combined==p+"-"+num.zfill(4),"combined key disagreement")
        pair=(norm(description),norm(category))
        require(all(pair),"blank dictionary text")
        if pair in entries[k]:duplicates+=1
        entries[k].add(pair);n+=1
    require(n==expected and n==sum(map(len,entries.values()))+duplicates,"dictionary reconciliation")
    return entries,{"rows":n,"distinct_keys":len(entries),"duplicate_normalized_rows":duplicates,
                    "multi_definition_keys":sum(len(v)>1 for v in entries.values()),
                    "keys_by_prefix":dict(Counter(k[0] for k in entries))}

def download():
    meta=cms.metadata(IDENT);n=cms.count(IDENT)
    require(meta["released"]==RELEASE and n==ROWS,"lookup release/count differs from qualified citation release")
    with cms.response(meta["url"]) as res:
        cms.allowed(res.geturl())
        data=res.read(MAX_BYTES+1)
    require(0<len(data)<=MAX_BYTES,"lookup size exceeds bound")
    require(cms.metadata(IDENT)==meta and cms.count(IDENT)==n,"lookup changed during download")
    return data,{"metadata":meta,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),"retrieved_at":datetime.now(timezone.utc).isoformat()}

def match(entries,tag,description,category):
    if not re.fullmatch(r"[FKE][0-9]{1,4}",tag):return "invalid_key"
    pairs=entries.get(key(tag[0],tag[1:]),set())
    if not pairs:return "key_missing"
    if (norm(description),norm(category)) in pairs:
        return "exact_text_multiple_definitions" if len(pairs)>1 else "exact_text_single_definition"
    if norm(description) in {d for d,c in pairs}:return "category_differs"
    return "description_differs"

def status_bucket(raw):
    current=correction_state(raw)
    if current!="unmapped":return current
    return STATUS_CANDIDATES.get(norm(raw),"unresolved_other")

def audit(db,entries,expected):
    out={}
    for dataset,n_expected in expected.items():
        row=db.execute("SELECT r.id,r.published_on FROM current_release c JOIN releases r ON r.id=c.release_id WHERE c.dataset=? AND r.dataset=c.dataset",(dataset,)).fetchone()
        require(row is not None,"citation release absent")
        rid,published=row;require(published==RELEASE,"citation release mismatch")
        dates=Counter();matches=Counter();statuses=Counter();unmapped=Counter();n=0
        for tag,desc,category,status,correction,survey,release_id in db.execute("SELECT tag,description,category,correction_status,correction_date,survey_date,release_id FROM findings WHERE dataset=?",(dataset,)):
            require(release_id==rid,"finding lineage mismatch")
            matches[match(entries,tag,desc,category)]+=1
            bucket=status_bucket(status);statuses[bucket]+=1
            if bucket=="unresolved_other":unmapped[norm(status)]+=1
            state=date_state(correction,date.fromisoformat(published))
            if state=="after_release":dates[bucket]+=1
            n+=1
        require(n==n_expected==sum(matches.values())==sum(statuses.values()),"citation reconciliation")
        out[dataset]={"rows":n,"lookup_match_counts":dict(matches),"correction_status_candidate_counts":dict(statuses),
                      "unresolved_other_distinct_normalized_values":len(unmapped),
                      "unresolved_other_frequency_distribution":sorted(unmapped.values(),reverse=True),
                      "after_release_correction_dates_by_status":dict(dates)}
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--cms-base",type=Path,required=True);p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit already exists")
    path=a.cms_base/"facilitysignal.sqlite3"
    require(sha(path)==BASE_SHA,"retained baseline checksum mismatch");validate_base(a.cms_base)
    data,meta=download();entries,summary=lookup(data,ROWS)
    with closing(readonly(path)) as db:
        result=audit(db,entries,EXPECTED)
    require(sha(path)==BASE_SHA,"source mutated")
    report={"lookup":meta|summary,"citation_source_sha256":BASE_SHA,"citation_rows":sum(EXPECTED.values()),"sources":result,
            "limits":"Aggregate only. Exact dictionary text agreement is not historical tag-version proof, current compliance, service demand, equipment evidence or a confirmed opportunity. Status candidates are literal comparisons only, not semantic promotion. No raw dictionary rows or provider records retained."}
    a.audit.parent.mkdir(parents=True,exist_ok=True)
    with a.audit.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
    print("CITATION_DICTIONARY_AUDIT",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":main()
