"""Bounded aggregate-only current-value check for historical CLIA domains and QIES references.

No linked facility records, IDs, names, addresses or raw source data are emitted.
Historical code labels are not current operation or canonical site claims.
"""
import argparse,csv,json,re,tempfile
from collections import Counter,defaultdict
from pathlib import Path
from collect_registry import source_encoding,open_csv
from restore_snapshot import materialize,verify_raw
from pos_raw_field_profile import read,need,LOCK,INVENTORY
ROOT=Path(__file__).resolve().parent
LAYOUT_SHA="8887f8603550af0ec6cb793b1f1fcb61afd5ab1bea4c1ca5701f592b56e7be65"
DOMAINS={
    "CRTFCT_TYPE_CD":{"1":"compliance","2":"waiver","3":"accreditation","4":"provider_performed_microscopy","9":"registration"},
    "APLCTN_TYPE_CD":{"1":"compliance","2":"waiver","3":"accreditation","4":"provider_performed_microscopy"},
    "CURRENT_CLIA_LAB_CLSFCTN_CD":{"00":"CLIA laboratory","05":"CLIA exempt laboratory","10":"CLIA VA laboratory"},
    "GNRL_FAC_TYPE_CD":dict(zip((f"{i:02d}" for i in range(1,30)),
        ("Ambulance","Ambulatory surgery center","Ancillary test site","Assisted living facility","Blood bank","Community clinic","Comprehensive outpatient rehabilitation","Dialysis","Federally qualified health center","Health fair","Health maintenance organization","Home health agency","Hospice","Hospital","Independent","Industrial","Insurance","Intermediate care","Mobile laboratory","Pharmacy","Physician office","Other practitioner","Prison","Public health laboratory","Rural health clinic","School/student health","Skilled nursing/nursing facility","Tissue bank/repository","Other"))),
    "CLIA_TRMNTN_CD":{f"{i:02d}":("historical_active_label" if i==0 else "historical_other_status") for i in (*range(18),20,33,80,99)},
    "CMPLNC_STUS_CD":{"A":"at_survey_in_compliance","B":"at_survey_not_in_compliance"},
    **{f:dict.fromkeys(("Y","N")) for f in ("MLT_SITE_EXCPTN_SW","HOSP_LAB_EXCPTN_SW","NON_PRFT_EXCPTN_SW","LAB_TEMP_TSTG_SITE_SW","SHR_LAB_SW")}
}
VOLUME_FIELDS=("FORM_116_ACRDTD_TEST_VOL_CNT","FORM_116_TEST_VOL_CNT","FORM_1557_TEST_VOL_CNT","PPMP_TEST_VOL_CNT","WVD_TEST_VOL_CNT","LAB_SITE_CNT")
Q_FIELDS=tuple("CLIA_ID_NUMBER_"+str(i) for i in range(1,6))
def domain(raw,allowed):
    token=raw.strip()
    return token if token in allowed else "blank" if not token else "unrecognized"
def quantity(raw):
    s=raw.strip()
    if not s:return "blank"
    if not re.fullmatch(r"[0-9]{1,15}",s):return "other"
    return "zero" if int(s)==0 else "positive"
def stream(path,pin,inv):
    verify_raw(path,pin)
    fields=[f["field"] for f in inv["fields"]]
    need(inv["source_sha256"]==pin["sha256"],"inventory digest")
    enc=source_encoding(path,pin["metadata"]["zipped"])
    n=0
    with open_csv(path,pin["metadata"]["zipped"],enc) as f:
        r=csv.DictReader(f);need(r.fieldnames==fields,"exact raw header")
        for row in r:
            need(None not in row and all(v is not None for v in row.values()),"malformed source row")
            n+=1
            yield row
    need(n==pin["input_rows"],"source row count")
    verify_raw(path,pin)

def audit(qpath,cpath,pins,inv):
    # Only the small set of hospital reference tokens is retained temporarily.
    refs=defaultdict(list)
    q=Counter()
    qscope=Counter()
    ref_fields={f:Counter() for f in Q_FIELDS}
    for ordinal,r in enumerate(stream(qpath,pins["qies"],inv["qies"]),1):
        category=r["PRVDR_CTGRY_CD"].strip()
        hospital=category in ("01","1")
        qscope["historical_hospital_category" if hospital else "other_category"]+=1
        seen=set()
        for f in Q_FIELDS:
            token=r[f].strip()
            bucket=ref_fields[f]
            if not token:bucket["blank"]+=1;continue
            bucket["nonblank"]+=1
            if not hospital:
                bucket["out_of_hospital_scope"]+=1;continue
            if token in seen:bucket["repeated_within_row"]+=1;continue
            seen.add(token)
            refs[token].append((ordinal,r["STATE_CD"].strip(),f))
            bucket["distinct_reference_occurrence"]+=1
        if seen:q["hospital_rows_with_reference"]+=1
    domains={f:Counter() for f in DOMAINS}
    volume={f:defaultdict(Counter) for f in VOLUME_FIELDS}
    matches=defaultdict(Counter)
    matched_rows=0
    lab=Counter()
    for r in stream(cpath,pins["clia"],inv["clia"]):
        lab["source_rows"]+=1
        certificate=domain(r["CRTFCT_TYPE_CD"],DOMAINS["CRTFCT_TYPE_CD"])
        for field,allowed in DOMAINS.items():domains[field][domain(r[field],allowed)]+=1
        for field in VOLUME_FIELDS:volume[field][certificate][quantity(r[field])]+=1
        token=r["PRVDR_NUM"].strip()
        if not token:lab["blank_identifier_rows"]+=1
        if token in refs:
            matched_rows+=1
            state=r["STATE_CD"].strip()
            for ordinal,qstate,field in refs[token]:
                # State corroboration is distinct from matching the publisher reference.
                state_agreement="same_state" if state and qstate and state==qstate else "state_conflict" if state and qstate else "state_missing"
                matches[(ordinal,token,field)][state_agreement]+=1
                matches[(ordinal,token,field)]["candidate_rows"]+=1
    n=lab["source_rows"]
    for c in domains.values():need(sum(c.values())==n,"code domain count reconciliation")
    for bycert in volume.values():
        need(sum(sum(c.values()) for c in bycert.values())==n,"volume count reconciliation")
    qmatched=set();matched_tokens=set();link=Counter()
    for token,items in refs.items():
        for ordinal,state,field in items:
            key=(ordinal,token,field)
            count=matches[key]["candidate_rows"]
            if not count:link["unmatched_reference_occurrences"]+=1;continue
            link["matched_reference_occurrences"]+=1
            link["candidate_lab_row_pairs"]+=count
            link["same_state_candidate_pairs"]+=matches[key]["same_state"]
            link["different_state_candidate_pairs"]+=matches[key]["state_conflict"]
            link["missing_state_candidate_pairs"]+=matches[key]["state_missing"]
            link["multiple_lab_row_candidates"]+=int(count>1)
            qmatched.add(ordinal);matched_tokens.add(token)
    need(link["matched_reference_occurrences"]+link["unmatched_reference_occurrences"]==sum(len(x) for x in refs.values()),"link occurrence reconciliation")
    need(link["candidate_lab_row_pairs"]==sum(link[k] for k in ("same_state_candidate_pairs","different_state_candidate_pairs","missing_state_candidate_pairs")),"candidate pairs reconciliation")
    return {"format_version":1,"source_hashes":{k:pins[k]["sha256"] for k in ("qies","clia")},
        "period":pins["clia"]["release"],"historical_clia_layout_sha256":LAYOUT_SHA,
        "historical_semantics_status":"provisional 2023 reference; actual 2026 exact literal domain observations",
        "clia_source_rows":n,"domain_counts":{f:dict(c) for f,c in domains.items()},
        "reference_domains":DOMAINS,
        "volume_value_states_by_certificate_code":{f:{k:dict(c) for k,c in by.items()} for f,by in volume.items()},
        "qies_scope_counts":dict(qscope),"qies_reference_field_counts":{f:dict(c) for f,c in ref_fields.items()},
        "links":{**dict(link),"distinct_qies_reference_tokens":len(refs),"distinct_matched_reference_tokens":len(matched_tokens),
            "qies_rows_with_reference":q["hospital_rows_with_reference"],"qies_rows_with_exact_lab_candidate":len(qmatched),
            "clia_rows_with_exact_reference_candidate":matched_rows},
        "limitations":["Exact identifier references only; repeated source rows, historical/terminated records and multi-site certificates remain distinct.",
            "Affiliated provider numbers are not interpreted as ownership or hospital affiliation without verified semantics.",
            "No individual links or identifiers, no canonical sites, no current operation, installed equipment or service demand.",
            "Volume states are lexical per certificate code; no sums, current test volume or cross-field aggregation. Historical applicability is not presumed."]}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path)
    a=p.parse_args();need(not a.output.exists(),"new output required")
    pins={s["key"]:s for s in read(LOCK)["sources"]}
    inv=read(INVENTORY)["registries"]
    legacy=read(ROOT/"research/clia_historical_dictionary_crosswalk_20261126.json")
    need(legacy["historical_layout"]["sha256"]==LAYOUT_SHA and legacy["raw_fields"]==103,"historical layout drift")
    with tempfile.TemporaryDirectory(prefix="clia-domain-link-") as d:
        q=materialize(pins["qies"],a.raw_dir,Path(d),a.download)
        c=materialize(pins["clia"],a.raw_dir,Path(d),a.download)
        result=audit(q,c,pins,inv)
    with a.output.open("x",encoding="utf-8") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print("CLIA_DOMAIN_LINK_AUDIT",json.dumps(result,separators=(",",":"),sort_keys=True),flush=True)
if __name__=="__main__":main()
