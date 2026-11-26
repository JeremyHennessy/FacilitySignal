"""Hospital service, infrastructure and workforce semantic evidence; aggregate only.

Use exact historical layout artifact and Q3 2026 raw data. Historical labels
are not current-version validation. No identifiers, individual observations,
installed equipment, current operation or market-size sums are published.
"""
import argparse,csv,hashlib,json,re,tempfile
from collections import Counter,defaultdict
from decimal import Decimal
from pathlib import Path
from restore_snapshot import materialize,verify_raw
from collect_registry import source_encoding,open_csv
from pos_raw_field_profile import read,need,LOCK,INVENTORY
from qies_hospital_services import REFERENCE,FIELDS as EXISTING
ROOT=Path(__file__).resolve().parent
LAYOUT_SHA="08291e4cd5d0221b1201d48be1d58a916af9ea4b608b90c4ebc5ae450ef1f4b7"
ARTIFACT_SHA="77babffa7f65e903664813f845ff68a182610d2ee9073fda8151241a28a3503d"
FIRST_HOSPITAL_SECTION=range(1,60)
AFF=("TOT_AFLTD_AMBLNC_SRVC_CNT","TOT_AFLTD_ASC_CNT","TOT_COLCTD_HOSP_CNT","TOT_AFLTD_ESRD_CNT","TOT_AFLTD_FQHC_CNT","TOT_AFLTD_HHA_CNT","TOT_AFLTD_HOSPC_CNT","TOT_AFLTD_OPO_CNT","TOT_AFLTD_PRTF_CNT","TOT_AFLTD_RHC_CNT","TOT_AFLTD_SNF_CNT")
OFF=("TOT_OFSITE_CNCR_HOSP_CNT","TOT_OFSITE_CHLDRN_HOSP_CNT","TOT_OFSITE_EMER_DEPT_CNT","TOT_OFSITE_INPTNT_LCTN_CNT","TOT_OFSITE_LTC_HOSP_CNT","TOT_OFSITE_OPTHLMC_SRGRY_CNT","TOT_OFSITE_OTHR_LCTN_CNT","TOT_OFSITE_PSYCH_HOSP_CNT","TOT_OFSITE_PSYCH_UNIT_CNT","TOT_OFSITE_REHAB_HOSP_CNT","TOT_OFSITE_REHAB_UNIT_CNT","TOT_OFSITE_URGNT_CARE_CNTR_CNT")
CAP=("CRTFD_BED_CNT","BED_CNT","CRDC_CTHRTZTN_PRCDR_ROOMS_CNT","ENDSCPY_PRCDR_ROOMS_CNT","PSYCH_UNIT_BED_CNT","REHAB_UNIT_BED_CNT")
FLAGS=("SKLTN_REC_SW","COLCTN_STUS_SW","LSC_WVR_SW","PSYCH_UNIT_SW","REHAB_UNIT_SW","SB_SW","OVRRD_BED_CNT_SW","OVRRD_STFG_SW")
STATUS=("PRVDR_CTGRY_SBTYP_CD","PGM_TRMNTN_CD","CMPLNC_STUS_CD","CRTFCTN_ACTN_TYPE_CD")
COUNTS=AFF+("AFLTD_PRVDR_CNT",)+OFF+("OFSITE_LCTN_CNT",)+CAP
REF_TEXT={"0":"NOTPROVIDED","1":"PROVIDEDBYSTAFF","2":"PROVIDEDUNDERARRANGEMENT","3":"PROVIDEDBYSTAFFANDUNDERARRANGEMENT"}
BUCKETS=("code00_same_state_hospital_candidate","code00_without_same_state_candidate","other_or_unknown_program_code")
MISSING={"":"blank","not available":"not_available","not applicable":"not_applicable","unknown":"literal_unknown"}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def compact(s):return "".join(s.upper().split())
def hospital_catalog(layout,pin):
    need(layout["historical_layout"]["sha256"]==LAYOUT_SHA and layout["source_sha256"]==pin["sha256"],"layout or source mismatch")
    exact={}
    for f in layout["fields"]:
        matches=[(d,o) for d in f["definitions"] for o in d["occurrences"]
                 if o["category_code"]=="01" and o["physical_pdf_page"] in FIRST_HOSPITAL_SECTION]
        if not matches:continue
        need(len(matches)==1,"unexpected duplicate first hospital section field")
        d,o=matches[0]
        exact[f["field"]]={"label":d["label_candidate"],"definition":d["description_candidate"],
                           "page":o["physical_pdf_page"],"printed_page":o["printed_page"],
                           "codes":dict(o["code_examples"])}
    services={k:v for k,v in exact.items() if k.endswith("_SRVC_CD")}
    need(len(services)==57 and set(EXISTING)<=set(services),"service field coverage mismatch")
    for k,d in services.items():
        need({c:compact(t) for c,t in d["codes"].items()}==REF_TEXT and
             d["definition"] and "how" in d["definition"].lower(),"historical service domain mismatch "+k)
    workforce={k:v for k,v in exact.items() if 56<=v["page"]<=59 and
               (v["definition"] or "").startswith(("Number of full-time equivalent","Total number of full-time equivalent"))}
    need(len(workforce)==20,"historical FTE field count")
    need(len(COUNTS)==31 and set(COUNTS+FLAGS+STATUS+("OPRTG_ROOM_CNT",))<=set(exact),"infrastructure catalog mismatch")
    for k in COUNTS:
        need(exact[k]["definition"] and "number" in exact[k]["definition"].lower(),"missing count definition "+k)
    need("ambulatory surgical center" in exact["OPRTG_ROOM_CNT"]["definition"].lower(),"operating room contradiction must be preserved")
    need(exact["PGM_TRMNTN_CD"]["codes"]["00"]=="ACTIVE PROVIDER","historical status domain mismatch")
    return exact,services,workforce
def service(v):
    s=v.strip()
    return "code_"+s if s in REFERENCE else MISSING.get(s.casefold(),"unrecognized")
def code(v,domain):
    s=v.strip()
    return "code_"+s if s in domain else MISSING.get(s.casefold(),"unrecognized")
def flag(v):
    s=v.strip()
    return {"Y":"literal_Y","N":"literal_N"}.get(s,MISSING.get(s.casefold(),"unrecognized"))
def number(v,fte=False):
    s=v.strip()
    if s.casefold() in MISSING:return MISSING[s.casefold()],None
    if len(s)>30 or not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?",s):return "unrecognized",None
    n=Decimal(s)
    if n<0:return "negative",None
    if not fte and n!=n.to_integral_value():return "noninteger",None
    return ("zero" if n==0 else "positive"),n
class Quantity:
    def __init__(self):self.states=Counter();self.min=None;self.max=None;self.sum=Decimal(0);self.decimal_spelling=0
    def add(self,raw,fte=False):
        state,n=number(raw,fte);self.states[state]+=1
        if n is not None:
            self.min=n if self.min is None else min(self.min,n)
            self.max=n if self.max is None else max(self.max,n)
            self.sum+=n
            if "." in raw:self.decimal_spelling+=1
    def result(self,n):
        need(sum(self.states.values())==n,"quantity reconciliation")
        return {"states":dict(self.states),"range":None if self.min is None else {"min":str(self.min),"max":str(self.max)},
                "numeric_sum_diagnostic_only":None if self.min is None else str(self.sum),
                "decimal_spelling_count":self.decimal_spelling}
def clean_text(s):return " ".join(s.strip().upper().split())
def load_public(root,pin):
    path=root/"web/public-directory/hospital.json";market=read(root/"web/market-summary.json")["sources"]["hospital"]
    d=read(path)
    need(sha(path)==market["sha256"] and d["source"]=="hospital" and d["release"]==pin["release"]==market["release"]
         and d["row_count"]==len(d["records"])==pin["stored_rows"]==market["rows"],"public comparison release mismatch")
    result=defaultdict(list)
    for r in d["records"]:
        need(set(r)=={"ccn","name","address","city","state","zip","capacity"},"public comparison schema")
        result[r["ccn"]].append(r)
    return result,{"sha256":market["sha256"],"release":pin["release"],"records":pin["stored_rows"]}
def identity(row,public):
    token=row["PRVDR_NUM"].strip()
    if not re.fullmatch(r"[A-Za-z0-9]{6}",token):return "non_six_character_id",[],[]
    candidates=public.get(token,[])
    if not candidates:return "no_exact_public_hospital_id",[],[]
    state=row["STATE_CD"].strip()
    same=[r for r in candidates if state and r["state"]==state]
    return ("same_state_candidate" if same else "id_candidate_state_conflict_or_missing"),candidates,same
def compare_totals(vals,total,components):
    if vals[total] is None or any(vals[k] is None for k in components):return "not_comparable"
    n=sum(vals[k] for k in components)
    return "equal" if n==vals[total] else "component_sum_above_reported_total" if n>vals[total] else "component_sum_below_reported_total"
def audit(raw,pin,inventory,layout,public,public_meta,prior):
    exact,svc,fte=hospital_catalog(layout,pin)
    header=[f["field"] for f in inventory["fields"]]
    need(inventory["source_sha256"]==pin["sha256"],"inventory mismatch")
    fields=tuple(svc)+COUNTS+tuple(fte)+FLAGS+STATUS
    need(len(set(fields))==len(fields) and set(fields+("OPRTG_ROOM_CNT",))<=set(header),"field set mismatch")
    scopes=("all",)+BUCKETS
    n=Counter();services={s:{k:Counter() for k in svc} for s in scopes}
    quantities={s:{k:Quantity() for k in COUNTS+tuple(fte)} for s in scopes}
    flags={s:{k:Counter() for k in FLAGS} for s in scopes}
    status={s:{k:Counter() for k in STATUS} for s in scopes}
    joints={s:defaultdict(Counter) for s in scopes}
    ident=Counter();pairs=Counter();matched_public=set();same_public=set();qies_per_public=Counter()
    blocked=Quantity();raw_rows=0
    verify_raw(raw,pin)
    enc=source_encoding(raw,pin["metadata"]["zipped"])
    with open_csv(raw,pin["metadata"]["zipped"],enc) as f:
        reader=csv.DictReader(f);need(reader.fieldnames==header,"raw header mismatch")
        for r in reader:
            raw_rows+=1
            need(None not in r and all(v is not None for v in r.values()),"malformed source row")
            need(r["PRVDR_CTGRY_CD"].strip() in ("01","1"),"nonhospital category requires separate review")
            relation,cands,same=identity(r,public);ident[relation]+=1
            pairs["exact_id_candidate_pairs"]+=len(cands);pairs["same_state_pairs"]+=len(same)
            for c in cands:matched_public.add((c["ccn"],c["state"]))
            for c in same:
                key=(c["ccn"],c["state"]);same_public.add(key);qies_per_public[key]+=1
                address=clean_text(r["ST_ADR"]);city=clean_text(r["CITY_NAME"]);zipcode=r["ZIP_CD"].strip()[:5]
                if address and city and zipcode and address==clean_text(c["address"]) and city==clean_text(c["city"]) and zipcode==c["zip"][:5]:
                    pairs["same_state_address_city_zip_text_corroborated"]+=1
            active=r["PGM_TRMNTN_CD"].strip()=="00"
            bucket=BUCKETS[0] if active and same else BUCKETS[1] if active else BUCKETS[2]
            vals={k:number(r[k])[1] for k in COUNTS}
            for s in ("all",bucket):
                n[s]+=1
                for k,v in services[s].items():v[service(r[k])]+=1
                for k,v in quantities[s].items():v.add(r[k],k in fte)
                for k,v in flags[s].items():v[flag(r[k])]+=1
                for k,v in status[s].items():v[code(r[k],exact[k]["codes"])]+=1
                joints[s]["affiliated_component_arithmetic"][compare_totals(vals,"AFLTD_PRVDR_CNT",AFF)]+=1
                joints[s]["offsite_component_arithmetic"][compare_totals(vals,"OFSITE_LCTN_CNT",OFF)]+=1
                a,b=vals["CRTFD_BED_CNT"],vals["BED_CNT"]
                joints[s]["certified_vs_total_beds"]["not_comparable" if a is None or b is None else "certified_above_total" if a>b else "certified_at_or_below_total"]+=1
                for flag_field,count_field in (("PSYCH_UNIT_SW","PSYCH_UNIT_BED_CNT"),("REHAB_UNIT_SW","REHAB_UNIT_BED_CNT")):
                    value=vals[count_field];joints[s][flag_field+"_vs_beds"][flag(r[flag_field])+"/"+("unknown" if value is None else "positive" if value>0 else "zero")]+=1
                room=vals["CRDC_CTHRTZTN_PRCDR_ROOMS_CNT"]
                joints[s]["cath_lab_service_vs_room_count"][service(r["CRDC_CTHRTZTN_LAB_SRVC_CD"])+"/"+("unknown" if room is None else "positive" if room>0 else "zero")]+=1
            blocked.add(r["OPRTG_ROOM_CNT"])
    verify_raw(raw,pin)
    need(raw_rows==pin["stored_rows"]==pin["input_rows"]==n["all"] and sum(n[s] for s in BUCKETS)==raw_rows,"source scope counts")
    need(sum(ident.values())==raw_rows and pairs["same_state_pairs"]<=pairs["exact_id_candidate_pairs"],"identity counts")
    for k,v in prior.items():need(dict(services["all"][k])==v,"existing 12 field distributions changed "+k)
    result={}
    for s in scopes:
        for group in (services[s],flags[s],status[s],joints[s]):
            need(all(sum(c.values())==n[s] for c in group.values()),"field count mismatch "+s)
        result[s]={"rows":n[s],"services":{k:dict(c) for k,c in services[s].items()},
             "counts":{k:quantities[s][k].result(n[s]) for k in COUNTS},
             "fte":{k:quantities[s][k].result(n[s]) for k in fte},
             "literal_flags":{k:dict(c) for k,c in flags[s].items()},
             "status_codes":{k:dict(c) for k,c in status[s].items()},
             "cross_checks":{k:dict(c) for k,c in joints[s].items()}}
    for k in svc:
        need(sum(sum(services[s][k].values()) for s in BUCKETS)==raw_rows,"service strata reconciliation")
    catalog={k:{**exact[k],"interpretation":"historical service provision code" if k in svc else "historical count" if k in COUNTS else "historical FTE" if k in fte else "literal flag check, publisher value domain not fully specified" if k in FLAGS else "historical source code"} for k in fields}
    return {"format_version":1,"source_sha256":pin["sha256"],"source_period":pin["release"],"source_rows":raw_rows,
      "historical_layout_sha256":LAYOUT_SHA,"historical_layout_artifact_sha256":ARTIFACT_SHA,
      "hospital_layout_scope":"first hospital category 01 section, physical pages 1-59; not other provider sections",
      "catalog":catalog,"field_counts":{"services":len(svc),"counts":len(COUNTS),"fte":len(fte),"literal_flags":len(FLAGS),"status_codes":len(STATUS),"blocked_count_field":1},
      "scope_results":result,"public_hospital_comparison":{**public_meta,"source_row_match_states":dict(ident),"candidate_pairs":dict(pairs),
      "distinct_public_id_state_candidates":len(matched_public),"distinct_public_same_state_candidates":len(same_public),
      "public_candidates_with_multiple_qies_rows":sum(x>1 for x in qies_per_public.values())},
      "blocked_field":{"field":"OPRTG_ROOM_CNT","reason":"First hospital section definition explicitly names an ambulatory surgical center. Do not interpret hospital room count from this field until resolved.",
          "historical_reference":exact["OPRTG_ROOM_CNT"],"lexical_numeric_diagnostic":blocked.result(raw_rows)},
      "limitations":["All raw values are aggregate only; source identifiers and individual observations never emitted.",
      "Historical 2023 dictionary labels are provisional for Q3 2026. Code 00 denotes historical program status, not current physical operation.",
      "Public comparison matches exact CCN and reported state; text corroboration is not canonical site resolution.",
      "Numeric sums and component comparisons are diagnostics, not approved market totals, unique sites, occupancy, installed equipment or staffing levels.",
      "A reported zero, blank, nonnumeric token and positive value remain separate; no service or procurement inference from missing data."]}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--layout",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--raw-dir",type=Path);p.add_argument("--download",action="store_true")
    a=p.parse_args();need(not a.output.exists(),"new output required");need(sha(a.layout)==ARTIFACT_SHA,"historical artifact hash mismatch")
    pins={s["key"]:s for s in read(LOCK)["sources"]};inv=read(INVENTORY)["registries"]["qies"]
    public,meta=load_public(ROOT,pins["hospital"]);prior=read(ROOT/"research/public_capability_audit_20261126.json")["qies_field_distributions"]
    with tempfile.TemporaryDirectory(prefix="qies-infrastructure-audit-") as d:
        raw=materialize(pins["qies"],a.raw_dir,Path(d),a.download)
        result=audit(raw,pins["qies"],inv,read(a.layout),public,meta,prior)
    with a.output.open("x",encoding="utf-8") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    summary={k:v for k,v in result.items() if k not in ("catalog","scope_results")}
    print("QIES_INFRASTRUCTURE_SUMMARY",json.dumps(summary,separators=(",",":"),sort_keys=True),flush=True)
    for k,c in result["catalog"].items():
        row={"field":k,"catalog":c,"scopes":{}}
        for s,v in result["scope_results"].items():
            group=next(g for g in ("services","counts","fte","literal_flags","status_codes") if k in v[g])
            row["scopes"][s]={"group":group,"value":v[group][k]}
        print("QIES_INFRASTRUCTURE_FIELD",json.dumps(row,separators=(",",":"),sort_keys=True),flush=True)
    for s,v in result["scope_results"].items():
        print("QIES_INFRASTRUCTURE_SCOPE",json.dumps({"scope":s,"rows":v["rows"],"cross_checks":v["cross_checks"]},separators=(",",":"),sort_keys=True),flush=True)
if __name__=="__main__":main()
