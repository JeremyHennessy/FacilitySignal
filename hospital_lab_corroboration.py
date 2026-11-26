"""Aggregate-only corroboration of hospital CLIA references, not a canonical site join."""
import argparse,json,tempfile,re
from collections import Counter,defaultdict
from pathlib import Path
from restore_snapshot import materialize
from clia_domain_link_audit import stream,Q_FIELDS,DOMAINS,domain,read,need,LOCK,INVENTORY
from qies_infrastructure_audit import load_public,identity,ROOT,clean_text

def location(r):
    z=r["ZIP_CD"].strip()
    return (r["STATE_CD"].strip(),clean_text(r["ST_ADR"]),clean_text(r["CITY_NAME"]),z[:5] if re.fullmatch(r"[0-9]{5}(?:-?[0-9]{4})?",z) else "")
def address_status(a,b):
    if not a[0] or not b[0]:return "missing_state"
    if a[0]!=b[0]:return "state_conflict"
    if not all(a[1:]+b[1:]):return "same_state_incomplete_address"
    if a[1:]==b[1:]:return "same_state_street_city_zip_agree"
    if a[2:]==b[2:]:return "same_state_city_zip_agree_street_differs"
    return "same_state_other_address_difference"
def audit(hospitals,labs,public):
    refs=defaultdict(list);cohorts=Counter();with_refs=Counter()
    for i,r in enumerate(hospitals):
        need(r["PRVDR_CTGRY_CD"].strip() in ("01","1"),"unexpected hospital category")
        relation,_,same=identity(r,public)
        bucket="code00_same_state_public_candidate" if r["PGM_TRMNTN_CD"].strip()=="00" and same else "code00_no_same_state_public_candidate" if r["PGM_TRMNTN_CD"].strip()=="00" else "other_program_code"
        cohorts[bucket]+=1
        tokens={r[f].strip() for f in Q_FIELDS if r[f].strip()}
        if tokens:with_refs[bucket]+=1
        for t in tokens:refs[t].append((i,bucket,location(r)))
    pairs=defaultdict(Counter);statuses=defaultdict(Counter);types=defaultdict(Counter);facility=defaultdict(Counter);flags=defaultdict(Counter);matches=Counter();seen=defaultdict(set)
    lab_rows=0
    for r in labs:
        lab_rows+=1;t=r["PRVDR_NUM"].strip()
        if t not in refs:continue
        matches[t]+=1
        for i,bucket,addr in refs[t]:
            pairs[bucket][address_status(addr,location(r))]+=1
            statuses[bucket][domain(r["CLIA_TRMNTN_CD"],DOMAINS["CLIA_TRMNTN_CD"])]+=1
            types[bucket][domain(r["CRTFCT_TYPE_CD"],DOMAINS["CRTFCT_TYPE_CD"])]+=1
            facility[bucket][domain(r["GNRL_FAC_TYPE_CD"],DOMAINS["GNRL_FAC_TYPE_CD"])]+=1
            flags[bucket][domain(r["MLT_SITE_EXCPTN_SW"],DOMAINS["MLT_SITE_EXCPTN_SW"])]+=1
            seen[bucket].add(i)
    totals=Counter()
    for token,items in refs.items():
        for _,bucket,_ in items:
            totals[bucket+"|reference_occurrences"]+=1
            totals[bucket+"|"+("unmatched" if matches[token]==0 else "unique_candidate" if matches[token]==1 else "multiple_candidates")]+=1
    for bucket in cohorts:
        n=sum(pairs[bucket].values())
        need(all(sum(x[bucket].values())==n for x in (statuses,types,facility,flags)),"pair reconciliation")
        need(len(seen[bucket])<=with_refs[bucket]<=cohorts[bucket],"hospital row reconciliation")
    return {"hospital_cohorts":cohorts,"hospital_rows_with_references":with_refs,"hospital_rows_with_matches":{k:len(v) for k,v in seen.items()},"reference_dispositions":totals,"lab_rows":lab_rows,"distinct_reference_tokens":len(refs),"matched_reference_tokens":len(matches),"pairs_by_address_evidence":pairs,"pairs_by_lab_status_literal":statuses,"pairs_by_certificate_literal":types,"pairs_by_general_facility_type_literal":facility,"pairs_by_multisite_exception_literal":flags}
def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path);a=p.parse_args()
    pins={x["key"]:x for x in read(LOCK)["sources"]};inv=read(INVENTORY)["registries"]
    public,meta=load_public(ROOT,pins["hospital"])
    prior=read(ROOT/"research/clia_domain_link_audit_20261126.json")
    need(prior["source_hashes"]=={k:pins[k]["sha256"] for k in ("qies","clia")},"prior source mismatch")
    with tempfile.TemporaryDirectory() as d:
        q=materialize(pins["qies"],a.raw_dir,Path(d),a.download);c=materialize(pins["clia"],a.raw_dir,Path(d),a.download)
        result=audit(stream(q,pins["qies"],inv["qies"]),stream(c,pins["clia"],inv["clia"]),public)
    need(sum(result["hospital_cohorts"].values())==13598 and result["lab_rows"]==686058,"row drift")
    need(result["distinct_reference_tokens"]==prior["links"]["distinct_qies_reference_tokens"] and result["matched_reference_tokens"]==prior["links"]["distinct_matched_reference_tokens"],"reference drift")
    need(sum(sum(x.values()) for x in result["pairs_by_address_evidence"].values())==prior["links"]["candidate_lab_row_pairs"],"pair drift")
    need(sum(v for x in result["pairs_by_address_evidence"].values() for k,v in x.items() if k.startswith("same_state_"))==prior["links"]["same_state_candidate_pairs"],"state drift")
    out={"source_hashes":prior["source_hashes"],"public_hospital":meta,"result":result,"limits":"Source rows and literal reference pairs only. Same address text is not physical-site proof. Program and certificate status literals are not current operation or validity. No new row-level publication."}
    with a.output.open("x") as f:json.dump(out,f,indent=2,sort_keys=True)
    print("HOSPITAL_LAB_CORROBORATION",json.dumps(out,sort_keys=True))
if __name__=="__main__":main()
