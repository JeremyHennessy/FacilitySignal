"""CLIA release-specific semantic diagnostics using retained publisher evidence.

One pinned file, one streaming pass. Only aggregate counts and bounded code
tokens are retained. Historical dictionary meanings remain provisional; no
individual laboratory, director, address, or contact values are emitted.
"""
import argparse,csv,hashlib,json,re,tempfile
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from restore_snapshot import materialize,verify_raw
from collect_registry import source_encoding,open_csv
from pos_raw_field_profile import read,need,LOCK,INVENTORY
from clia_domain_link_audit import DOMAINS
ROOT=Path(__file__).resolve().parent
LAYOUT_SHA="8887f8603550af0ec6cb793b1f1fcb61afd5ab1bea4c1ca5701f592b56e7be65"
ARTIFACT_SHA="23eb5208fd333ae52105a1e674268b713eec3dc89edd4d6fe697f18aed0e8b9b"
END=date(2026,9,30)
ACC=("A2LA","AABB","AOA","ASHI","CAP","COLA","JCAHO")
CLASS_FIELDS=tuple("CLIA_LAB_CLASSIFICATION_CD_"+str(i) for i in range(1,11))
AFF_FIELDS=tuple("AFFILIATED_PROVIDER_NUMBER_"+str(i) for i in range(1,9))
DATES=("CHOW_DT","CHOW_PRIOR_DT","CRTFCTN_DT","ORGNL_PRTCPTN_DT","TRMNTN_EXPRTN_DT","APLCTN_RCVD_DT","CRTFCT_EFCTV_DT","CRTFCT_MAIL_DT")+tuple(x+"_ACRDTD_Y_MATCH_DT" for x in ACC)
FLAGS=("ACPTBL_POC_SW","ELGBLTY_SW","SKLTN_REC_SW","MLT_SITE_EXCPTN_SW","HOSP_LAB_EXCPTN_SW","NON_PRFT_EXCPTN_SW","LAB_TEMP_TSTG_SITE_SW","SHR_LAB_SW")+tuple(x+"_ACRDTD_Y_MATCH_SW" for x in ACC)
CODE_FIELDS=("PRVDR_CTGRY_SBTYP_CD","PRVDR_CTGRY_CD","CMPLNC_STUS_CD","PGM_TRMNTN_CD","CRTFCTN_ACTN_TYPE_CD","GNRL_CNTL_TYPE_CD","APLCTN_TYPE_CD","GNRL_FAC_TYPE_CD","CRTFCT_TYPE_CD","CURRENT_CLIA_LAB_CLSFCTN_CD","CLIA_TRMNTN_CD","ACRDTN_SCHDL_CD","FORM_1557_CRTFCT_SCHDL_CD","FORM_1557_CMPLNC_SCHDL_CD")+CLASS_FIELDS+tuple(x+"_ACRDTD_CD" for x in ACC)
COUNTS=("CHOW_CNT","FORM_116_ACRDTD_TEST_VOL_CNT","FORM_116_TEST_VOL_CNT","DRCTLY_AFLTD_LAB_CNT","LAB_SITE_CNT","PPMP_TEST_VOL_CNT","FORM_1557_TEST_VOL_CNT","WVD_TEST_VOL_CNT")
REF_FIELDS=("CROSS_REF_PROVIDER_NUMBER","CLIA_MDCR_NUM","RELATED_PROVIDER_NUMBER","SHARED_LAB_XREF_NUMBER")+AFF_FIELDS
RESTRICTED={"PHNE_NUM","FAX_PHNE_NUM"}
IDENTITY={"PRVDR_NUM","FAC_NAME","ADDTNL_FAC_NAME","MDCD_VNDR_NUM"}
GEO={"CITY_NAME","SSA_CNTY_CD","RGN_CD","STATE_CD","SSA_STATE_CD","STATE_RGN_CD","ST_ADR","ZIP_CD","FIPS_STATE_CD","FIPS_CNTY_CD","CBSA_URBN_RRL_IND","CBSA_CD","ADDTNL_ST_ADR"}
ADMIN={"INTRMDRY_CARR_CD","INTRMDRY_CARR_PRIOR_CD","FY_END_MO_DAY_CD"}
MISSING={"":"blank","not available":"not_available","not applicable":"not_applicable","unknown":"literal_unknown"}
TERMS={"PGM_TRMNTN_CD","CLIA_TRMNTN_CD"}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def literal_code(raw,domain,term=False):
    v=raw.strip()
    if v in domain:return "code_"+v
    if v.casefold() in MISSING:return MISSING[v.casefold()]
    # A two-digit code from these specific regulatory fields is nonidentifying;
    # preserve exact unknown codes without revealing arbitrary source strings.
    if term and re.fullmatch(r"[0-9]{2}",v):return "unmapped_code_"+v
    return "unrecognized"
def flag(raw):
    s=raw.strip()
    return {"Y":"literal_Y","N":"literal_N"}.get(s,MISSING.get(s.casefold(),"unrecognized"))
def quantity(raw):
    s=raw.strip()
    if s.casefold() in MISSING:return MISSING[s.casefold()]
    if len(s)>15 or not re.fullmatch(r"[+-]?[0-9]+",s):return "unrecognized"
    n=int(s)
    return "negative" if n<0 else "zero" if n==0 else "positive"
def parse_date(raw):
    s=raw.strip()
    if s.casefold() in MISSING:return MISSING[s.casefold()],None
    def build(y,m,d):
        try:return date(int(y),int(m),int(d))
        except ValueError:return None
    ds=[]
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",s):
        x=build(*s.split("-"));kind="iso"
        if x:ds=[x]
    elif re.fullmatch(r"[0-9]{8}",s):
        x=build(s[:4],s[4:6],s[6:]);kind="compact_yyyymmdd"
        if x:ds=[x]
    elif re.fullmatch(r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}",s):
        a,b,y=s.split("/")
        ds=list({d for d in (build(y,a,b),build(y,b,a)) if d});kind="slash"
    else:return "unrecognized_format",None
    if not ds:return "invalid_calendar_date",None
    if len(ds)>1:return "ambiguous_slash",None
    d=ds[0]
    return kind+("_after_release_end" if d>END else "_on_or_before_release_end"),d
def date_relation(a,b):
    return "not_comparable" if a is None or b is None else "before" if a<b else "equal" if a==b else "after"
def ref_shape(s):
    v=s.strip()
    if not v:return "blank"
    if re.fullmatch(r"[0-9]{2}D[0-9]{7}",v):return "clia_shaped"
    if re.fullmatch(r"[A-Z0-9]{6}",v):return "six_character_alphanumeric"
    if re.fullmatch(r"[A-Z0-9]{10}",v):return "other_ten_character_alphanumeric"
    return "other_nonblank"
def classify_field(f):
    if f in RESTRICTED:return "restricted_contact","Presence only; no contact publication or numeric conversion."
    if f in IDENTITY:return "identity","Reported source identifier/name; not a canonical site or legal entity."
    if f in GEO:return "geography","Reported geography or location metadata; not site verification. Preserve text and leading zeros."
    if f in ADMIN:return "administrative","Administrative source context; no current contractor or fiscal-date inference."
    if f in REF_FIELDS:return "reference","Exact token candidate research only. Meaning of numbered affiliations or cross-references requires corroboration."
    if f in DATES:return "date","Field-specific historical date meaning. Preserve ambiguous dates; termination/expiration is a dual-purpose field."
    if f in COUNTS:return "quantity","Field-specific count or estimated annual volume; preserve zero/blank, certificate applicability and overlapping measures. No sum as equipment or actual throughput."
    if f in FLAGS:return "indicator","Reported literal flag; not an independently validated status, exemption or installed asset."
    if f in CODE_FIELDS:return "coded_classification","Compare exact historical publisher code domain. No blanket current-version approval or current operations inference."
    raise ValueError("Unclassified header "+f)
def catalog(layout,pin,inventory,raw_profile):
    need(layout["historical_layout"]["sha256"]==LAYOUT_SHA and layout["source_sha256"]==pin["sha256"],"historical artifact mismatch")
    expected=[x["field"] for x in inventory["fields"]]
    need(len(expected)==103 and inventory["source_sha256"]==pin["sha256"],"header inventory mismatch")
    need(raw_profile["source_sha256"]==pin["sha256"] and [x["field"] for x in raw_profile["fields"]]==expected,"raw profile mismatch")
    result={}
    for i,(f,p) in enumerate(zip(layout["fields"],raw_profile["fields"]),1):
        k=f["field"];need(k==expected[i-1]==p["field"] and f["ordinal"]==i,"header order mismatch")
        matches=[(d,o) for d in f["definitions"] for o in d["occurrences"] if o["category_code"]=="22"]
        need(len(matches)==1,"ambiguous historical CLIA definition "+k)
        d,o=matches[0]
        need(bool(d["description_candidate"]),"missing historical definition")
        codes=dict(o["code_examples"])
        need(len(codes)==len(o["code_examples"]),"duplicated historical code "+k)
        typ,use=classify_field(k)
        result[k]={"ordinal":i,"field":k,"category":typ,"historical_definition":d["description_candidate"],"label_candidate":d["label_candidate"],
          "historical_page":o["physical_pdf_page"],"printed_page":o["printed_page"],
          "historical_type":d["type_candidate"],"historical_codes":codes if k in CODE_FIELDS else {},
          "raw_presence_and_shape":{x:p[x] for x in ("states","distinct_nonmissing","lexical_shapes")},
          "use_limit":use,"semantic_status":"historical_2023_publisher_reference_only",
          "new_row_level_publication":"not_authorized"}
    need(set(result)==set(expected),"catalog coverage")
    need(all(result[k]["historical_codes"] for k in CODE_FIELDS),"missing bounded domain")
    for k in TERMS:need(set(result[k]["historical_codes"])==set(DOMAINS["CLIA_TRMNTN_CD"]),"termination reference domain changed")
    return result
def scope(term):
    return "literal_00" if term=="code_00" else "other_documented" if term.startswith("code_") else "unresolved"
def audit(path,pin,inventory,layout,raw_profile,prior):
    meta=catalog(layout,pin,inventory,raw_profile);header=list(meta)
    code_maps={k:meta[k]["historical_codes"] for k in CODE_FIELDS}
    codes={k:Counter() for k in CODE_FIELDS}
    flags={k:Counter() for k in FLAGS};dates={k:Counter() for k in DATES}
    counts={k:Counter() for k in COUNTS};refs={k:Counter() for k in REF_FIELDS}
    terms=Counter();terms_scope=Counter();scope_counts=Counter()
    date_by_scope=defaultdict(Counter);cert_by_scope=defaultdict(Counter);facility_by_scope=defaultdict(Counter)
    accreditation={k:Counter() for k in ACC};acc_scope={k:defaultdict(Counter) for k in ACC}
    volume_by_cert={k:defaultdict(Counter) for k in COUNTS[1:]}
    class_history=Counter();class_current=Counter();multi=Counter();date_checks=Counter()
    lab_ids=Counter();aff_tokens=Counter();aff_self=0;aff_distinct_rows=Counter();n=0
    verify_raw(path,pin)
    with open_csv(path,pin["metadata"]["zipped"],source_encoding(path,pin["metadata"]["zipped"])) as f:
        reader=csv.DictReader(f);need(reader.fieldnames==header,"exact CLIA header mismatch")
        for r in reader:
            n+=1;need(None not in r and all(x is not None for x in r.values()),"malformed source row")
            cv={k:literal_code(r[k],v,k in TERMS) for k,v in code_maps.items()}
            fv={k:flag(r[k]) for k in FLAGS}
            dv={k:parse_date(r[k]) for k in DATES}
            qv={k:quantity(r[k]) for k in COUNTS}
            for k,v in cv.items():codes[k][v]+=1
            for k,v in fv.items():flags[k][v]+=1
            for k,v in dv.items():dates[k][v[0]]+=1
            for k,v in qv.items():counts[k][v]+=1
            lab=r["PRVDR_NUM"].strip()
            if lab:lab_ids[lab]+=1
            unique=set()
            for k in REF_FIELDS:
                token=r[k].strip();refs[k][ref_shape(token)]+=1
                if k in AFF_FIELDS and token:
                    unique.add(token);aff_tokens[token]+=1;aff_self+=int(token==lab and bool(lab))
            aff_distinct_rows[str(len(unique))]+=1
            p,c=cv["PGM_TRMNTN_CD"],cv["CLIA_TRMNTN_CD"]
            terms[p+"/"+c]+=1
            s=scope(c);scope_counts[s]+=1
            terms_scope[scope(p)+"/"+s]+=1
            cert=cv["CRTFCT_TYPE_CD"]
            cert_by_scope[s][cert]+=1
            facility_by_scope[s][cv["GNRL_FAC_TYPE_CD"]]+=1
            for k in ("TRMNTN_EXPRTN_DT","CRTFCT_EFCTV_DT","CRTFCT_MAIL_DT"):
                date_by_scope[s+"/"+k][dv[k][0]]+=1
            date_checks["effective_vs_termination_or_expiration/"+date_relation(dv["CRTFCT_EFCTV_DT"][1],dv["TRMNTN_EXPRTN_DT"][1])]+=1
            hist=[cv[k] for k in CLASS_FIELDS]
            known=[v for v in hist if v.startswith("code_")]
            class_history[str(len(known))]+=1
            cur=cv["CURRENT_CLIA_LAB_CLSFCTN_CD"]
            class_current["current_in_reported_history" if cur in known else "current_not_in_reported_history"]+=1
            for k in ACC:
                reported=cv[k+"_ACRDTD_CD"];confirmed=fv[k+"_ACRDTD_Y_MATCH_SW"];dt=dv[k+"_ACRDTD_Y_MATCH_DT"][0]
                label=reported+"/"+confirmed+"/"+("date_blank" if dt=="blank" else "date_present")
                accreditation[k][label]+=1;acc_scope[k][s][label]+=1
            for k in COUNTS[1:]:volume_by_cert[k][cert][qv[k]]+=1
            multi[fv["MLT_SITE_EXCPTN_SW"]+"/"+qv["LAB_SITE_CNT"]]+=1
    verify_raw(path,pin);need(n==pin["stored_rows"]==pin["input_rows"],"CLIA count mismatch")
    for group in (codes,flags,dates,counts,refs,accreditation):
        need(all(sum(v.values())==n for v in group.values()),"field count reconciliation")
    need(sum(terms.values())==sum(terms_scope.values())==sum(scope_counts.values())==sum(class_history.values())==sum(class_current.values())==sum(multi.values())==sum(aff_distinct_rows.values())==n,"joint counts")
    # Reconcile prior audit without replacing its observations or guessing unknown codes.
    for k,old in prior["domain_counts"].items():
        if k in codes:
            now=Counter()
            for token,c in codes[k].items():
                now[token[5:] if token.startswith("code_") else "blank" if token=="blank" else "unrecognized"]+=c
        elif k in flags:
            now=Counter()
            for token,c in flags[k].items():now[token[-1] if token.startswith("literal_") else token]+=c
        else:continue
        need(dict(now)==old,"prior CLIA domain mismatch "+k)
    for k,m in prior["volume_value_states_by_certificate_code"].items():
        now={c[5:] if c.startswith("code_") else c:dict(v) for c,v in volume_by_cert[k].items()}
        need(now==m,"prior volume reconciliation "+k)
    for k,v in meta.items():
        v["actual_review"]="bounded_code_domain_counts" if k in codes else "literal_flag_counts" if k in flags else "conservative_date_states" if k in dates else "quantity_states" if k in counts else "reference_shape_counts" if k in refs else "existing_aggregate_lexical_profile"
    return {"format_version":1,"as_of":"2026-11-26","source_sha256":pin["sha256"],"period":pin["release"],"source_rows":n,
      "historical_layout_sha256":LAYOUT_SHA,"historical_layout_artifact_sha256":ARTIFACT_SHA,
      "catalog":list(meta.values()),"code_counts":{k:dict(v) for k,v in codes.items()},
      "literal_flag_counts":{k:dict(v) for k,v in flags.items()},
      "date_states":{k:dict(v) for k,v in dates.items()},"quantity_states":{k:dict(v) for k,v in counts.items()},
      "reference_shape_counts":{k:dict(v) for k,v in refs.items()},
      "termination_code_pairs":dict(terms),"termination_scope_pairs":dict(terms_scope),
      "clia_term_scope_rows":dict(scope_counts),
      "certificate_by_clia_term_scope":{k:dict(v) for k,v in cert_by_scope.items()},
      "facility_type_by_clia_term_scope":{k:dict(v) for k,v in facility_by_scope.items()},
      "date_states_by_clia_term_scope":{k:dict(v) for k,v in date_by_scope.items()},
      "date_order_diagnostics":dict(date_checks),"classification_history_populated_count":dict(class_history),
      "current_class_history_corroboration":dict(class_current),
      "accreditation_report_confirmation_date_presence":{k:dict(v) for k,v in accreditation.items()},
      "accreditation_by_clia_term_scope":{k:{s:dict(v) for s,v in m.items()} for k,m in acc_scope.items()},
      "quantity_states_by_certificate_code":{k:{c:dict(v) for c,v in m.items()} for k,m in volume_by_cert.items()},
      "multi_site_flag_and_count":dict(multi),
      "identity_and_reference_diagnostics":{"nonblank_registry_ids":sum(lab_ids.values()),"distinct_registry_id_tokens":len(lab_ids),
         "registry_id_tokens_with_multiple_rows":sum(x>1 for x in lab_ids.values()),
         "affiliation_reference_occurrences":sum(aff_tokens.values()),"distinct_affiliation_reference_tokens":len(aff_tokens),
         "affiliation_occurrences_matching_registry_id":sum(v for k,v in aff_tokens.items() if k in lab_ids),
         "distinct_affiliation_tokens_matching_registry_id":len(set(aff_tokens)&set(lab_ids)),
         "affiliation_self_reference_occurrences":aff_self,"distinct_affiliation_tokens_per_row":dict(aff_distinct_rows)},
      "limits":["Source file is historical; the 2023 field dictionary remains provisional for 2026.",
         "Literal 00 is historical active-status label, not independently verified current certificate validity or operation.",
         "Both termination columns remain separate; exact exported mapping to provider/current/pending certificate levels is not assumed.",
         "TRMNTN_EXPRTN_DT can be termination or expiration, and a future date is not proof of active certification.",
         "Accreditation application declaration, confirmation flag and date presence differ; no current accreditation claim.",
         "Affiliation token matches are not verified relationships or ownership. No raw identifiers, dates, names or addresses emitted.",
         "Volume count fields differ in scope and certificate type; no total tests, capacity, or installed equipment inference."]}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--layout",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--raw-dir",type=Path);p.add_argument("--download",action="store_true")
    a=p.parse_args();need(not a.output.exists(),"new output required");need(sha(a.layout)==ARTIFACT_SHA,"historical artifact hash mismatch")
    pin=next(s for s in read(LOCK)["sources"] if s["key"]=="clia")
    inv=read(INVENTORY)["registries"]["clia"]
    profile=read(ROOT/"research/clia_raw_field_profile_20261126.json")
    prior=read(ROOT/"research/clia_domain_link_audit_20261126.json")
    with tempfile.TemporaryDirectory(prefix="clia-certificate-audit-") as d:
        raw=materialize(pin,a.raw_dir,Path(d),a.download)
        result=audit(raw,pin,inv,read(a.layout),profile,prior)
    with a.output.open("x",encoding="utf-8") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print("CLIA_CERTIFICATE_SUMMARY",json.dumps({k:v for k,v in result.items() if k!="catalog"},separators=(",",":"),sort_keys=True),flush=True)
    for f in result["catalog"]:print("CLIA_CERTIFICATE_FIELD",json.dumps(f,separators=(",",":"),sort_keys=True),flush=True)
if __name__=="__main__":main()
