"""Generate only the explicitly specified public aggregate evidence projection."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def read(path):
    return json.loads(path.read_text(encoding="utf-8"))
def qualify_clia_semantic(a,prior,ledger):
    pin=next(s for s in ledger["sources"] if s["key"]=="clia")
    n=a["source_rows"]
    if a["qualification_run"]!=45831429985 or a["qualification_result"]!="success" or a["source_sha256"]!=pin["sha256"] or n!=pin["stored_rows"] or a["period"]!=pin["release"]:
        raise ValueError("CLIA semantic source mismatch")
    catalog=a["catalog"]
    if len(catalog)!=103 or len({f["field"] for f in catalog})!=103 or [f["ordinal"] for f in catalog]!=list(range(1,104)):
        raise ValueError("CLIA semantic field inventory mismatch")
    if a["historical_layout_sha256"]!="8887f8603550af0ec6cb793b1f1fcb61afd5ab1bea4c1ca5701f592b56e7be65" or a["historical_layout_artifact_sha256"]!="23eb5208fd333ae52105a1e674268b713eec3dc89edd4d6fe697f18aed0e8b9b":
        raise ValueError("CLIA historical reference mismatch")
    def counts(v,total):
        if any(type(x) is not int or x<0 for x in v.values()) or sum(v.values())!=total:
            raise ValueError("CLIA count reconciliation failed")
    for group in ("code_counts","date_states","literal_flag_counts","reference_shape_counts","quantity_states"):
        for c in a[group].values():counts(c,n)
    term=a["code_counts"]["CLIA_TRMNTN_CD"]
    if a["code_counts"]["PGM_TRMNTN_CD"]!=term or a["termination_code_pairs"]!={f"{k}/{k}":v for k,v in term.items()}:
        raise ValueError("CLIA termination columns no longer agree")
    scopes=a["clia_term_scope_rows"]
    expected={"literal_00":term["code_00"],"other_documented":sum(v for k,v in term.items() if k.startswith("code_") and k!="code_00"),"unresolved":term["unmapped_code_95"]}
    if scopes!=expected or a["termination_scope_pairs"]!={f"{k}/{k}":v for k,v in scopes.items()}:
        raise ValueError("CLIA termination scope mismatch")
    counts(scopes,n)
    cert=a["certificate_by_clia_term_scope"]
    facilities=a["facility_type_by_clia_term_scope"]
    for group,field in ((cert,"CRTFCT_TYPE_CD"),(facilities,"GNRL_FAC_TYPE_CD")):
        if set(group)!=set(scopes):raise ValueError("CLIA scope missing")
        all_codes=a["code_counts"][field]
        for sc,values in group.items():
            counts(values,scopes[sc])
            if set(values)-set(all_codes):raise ValueError("CLIA classification domain mismatch")
        if {k:sum(group[sc].get(k,0) for sc in scopes) for k in all_codes}!=all_codes:
            raise ValueError("CLIA cross-scope totals mismatch")
        if prior is None or prior["source_hashes"]["clia"]!=pin["sha256"] or {"code_"+k:v for k,v in prior["domain_counts"][field].items()}!=all_codes:
            raise ValueError("CLIA prior qualified domain mismatch")
    old_term=prior["domain_counts"]["CLIA_TRMNTN_CD"]
    if {**{"code_"+k:v for k,v in old_term.items() if k!="unrecognized"},"unmapped_code_95":old_term["unrecognized"]}!=term:
        raise ValueError("CLIA prior termination distribution mismatch")
    accred={}
    yes="code_X/literal_Y/date_present";no="code_X/literal_N/date_blank";blank="blank/literal_N/date_blank"
    organizations={"A2LA","AABB","AOA","ASHI","CAP","COLA","JCAHO"}
    if set(a["accreditation_report_confirmation_date_presence"])!=organizations or set(a["accreditation_by_clia_term_scope"])!=organizations:
        raise ValueError("CLIA accreditation field set mismatch")
    for k,v in a["accreditation_report_confirmation_date_presence"].items():
        counts(v,n)
        if set(v)-{yes,no,blank}:raise ValueError("CLIA accreditation pattern changed")
        scoped=a["accreditation_by_clia_term_scope"][k]
        if set(scoped)!=set(scopes):raise ValueError("CLIA accreditation scope mismatch")
        for sc,c in scoped.items():
            counts(c,scopes[sc])
            if set(c)-{yes,no,blank}:raise ValueError("CLIA accreditation scoped pattern changed")
        if any(sum(c.get(pattern,0) for c in scoped.values())!=v.get(pattern,0) for pattern in (yes,no,blank)):
            raise ValueError("CLIA accreditation aggregate mismatch")
        accred[k]={"reported":v.get(yes,0)+v.get(no,0),"confirmed":v.get(yes,0),"unconfirmed":v.get(no,0),"code00_confirmed":scoped["literal_00"].get(yes,0)}
    dates={}
    for sc in scopes:
        for f in ("CRTFCT_EFCTV_DT","TRMNTN_EXPRTN_DT","CRTFCT_MAIL_DT"):
            k=sc+"/"+f;c=a["date_states_by_clia_term_scope"][k];counts(c,scopes[sc])
            before=c.get("compact_yyyymmdd_on_or_before_release_end",0);after=c.get("compact_yyyymmdd_after_release_end",0)
            dates[k]={"before":before,"after":after,"other":scopes[sc]-before-after}
    identity=a["identity_and_reference_diagnostics"];counts(identity["distinct_affiliation_tokens_per_row"],n)
    counts(a["current_class_history_corroboration"],n)
    counts(a["date_order_diagnostics"],n)
    counts(a["multi_site_flag_and_count"],n)
    if identity["affiliation_occurrences_matching_registry_id"]>identity["affiliation_reference_occurrences"] or identity["distinct_registry_id_tokens"]!=n:
        raise ValueError("CLIA identifier count mismatch")
    return {"scopes":scopes,"certificates":{sc:{k:cert[sc].get(k,0) for k in a["code_counts"]["CRTFCT_TYPE_CD"]} for sc in scopes},"facility_all":a["code_counts"]["GNRL_FAC_TYPE_CD"],"facility_00":{k:facilities["literal_00"].get(k,0) for k in a["code_counts"]["GNRL_FAC_TYPE_CD"]},
            "accreditation":accred,"dates":dates,"identity":identity,"field_count":len(catalog),
            "unmatched_references":identity["affiliation_reference_occurrences"]-identity["affiliation_occurrences_matching_registry_id"],
            "history_match":a["current_class_history_corroboration"]["current_in_reported_history"],
            "reversed_dates":a["date_order_diagnostics"]["effective_vs_termination_or_expiration/after"],"multisite":a["multi_site_flag_and_count"]}
def build(ledger,cap,spec,data_use=None):
    epa=next(x for x in ledger["sources"] if x["id"]=="FS-157")
    ctx={"ledger":ledger,"cap":cap,"epa":epa}
    if data_use is None:
        path=ROOT/"research/qualified_data_use_20261126.json"
        if path.exists():data_use=read(path)
    if data_use is not None:ctx["data_use"]=data_use
    clia_path=ROOT/"research/clia_domain_link_audit_20261126.json"
    if clia_path.exists():ctx["clia_audit"]=read(clia_path)
    nursing_path=ROOT/"research/nursing_semantic_audit_20261126.json"
    if nursing_path.exists():
        nursing=read(nursing_path)
        groups={a["group"]:a["result"] for a in nursing["audits"]}
        if set(groups)!={"chains","citations"} or nursing["qualification_run"]!=45826186143:
            raise ValueError("Unexpected nursing semantic audit")
        for name,s in groups["citations"].items():
            if any(sum(c.values())!=s["rows"] or set(c)-{"yes","no"} for c in s["flags"].values()):
                raise ValueError("Nursing flag domain or count mismatch")
            s["flag_yes"]={f:c.get("yes",0) for f,c in s["flags"].items()}
        ctx["nursing_semantic"]=groups
    pecos_path=ROOT/"research/pecos_role_semantic_audit_20261126.json"
    followup_path=ROOT/"research/pecos_semantic_followup_20261126.json"
    if pecos_path.exists() and followup_path.exists():
        pecos=read(pecos_path);follow=read(followup_path)
        pins={s["key"]:s for s in read(ROOT/"research/snapshot_release_20261125.json")["sources"]}
        if pecos["qualification_run"]!=45828076053 or follow["qualification_run"]!=45828422101:
            raise ValueError("Unqualified PECOS evidence")
        if set(pecos["sources"])!={f+"-"+s for f in ("hospital","snf") for s in ("enrollment","owner","chow")}:
            raise ValueError("Unexpected PECOS source set")
        for k,s in pecos["sources"].items():
            if any(s[f]!=pins[k][f] for f in ("sha256","stored_rows","input_rows","excluded_rows","release")):
                raise ValueError("PECOS release mismatch")
        for k,h in follow["source_hashes"].items():
            if pins[k]["sha256"]!=h:raise ValueError("Follow-up release mismatch")
        for fam,v in pecos["families"].items():
            own=v["owner"];n=own["counts"]["organizational_rows"]
            if n!=pins[fam+"-owner"]["stored_rows"] or own["role_text_agreement"]!={"matches":n} or sum(own["role_class_counts"].values())!=n:
                raise ValueError("Role reconciliation failed")
            if any(sum(x["rows"].values())!=n for x in own["flags"].values()):
                raise ValueError("Flag reconciliation failed")
            for c in ("direct_ownership","indirect_ownership","management","financial_interest","partnership","other","additional_disclosable_party","trustee"):
                if c not in own["role_class_counts"]:own["role_class_counts"][c]=None
            for c in ("AM","CH","CO"):
                v["chow"]["code_counts"].setdefault(c,0)
            label=follow["result"][fam+"-chow"]["counts"]
            if sum(label.get(k,0) for k in ("current_dictionary","documented_earlier_dictionary_variant"))!=pins[fam+"-chow"]["stored_rows"]:
                raise ValueError("CHOW wording not reconciled")
        subgroup=follow["result"]["hospital-enrollment"]
        if subgroup["rows"]!=pins["hospital-enrollment"]["stored_rows"] or any(sum(x.values())!=subgroup["rows"] or set(x)-{"yes","no"} for x in subgroup["subgroup_flag_counts"].values()):
            raise ValueError("Subgroup reconciliation failed")
        ctx["pecos_semantic"]=pecos
        ctx["pecos_followup"]=follow["result"]
    hospital_path=ROOT/"research/qies_hospital_infrastructure_audit_20261126.json"
    if hospital_path.exists():
        hospital=read(hospital_path)
        pins={s["key"]:s for s in read(ROOT/"research/snapshot_release_20261125.json")["sources"]}
        if hospital["qualification_run"]!=45829855217 or hospital["source_sha256"]!=pins["qies"]["sha256"] or hospital["source_rows"]!=pins["qies"]["stored_rows"]:
            raise ValueError("QIES infrastructure source mismatch")
        if hospital["historical_layout_sha256"]!="08291e4cd5d0221b1201d48be1d58a916af9ea4b608b90c4ebc5ae450ef1f4b7":
            raise ValueError("Historical layout mismatch")
        all_rows=hospital["scope_results"]["all"]
        for f,counts in cap["qies_field_distributions"].items():
            if all_rows["services"][f]!=counts:raise ValueError("Prior QIES field mismatch")
        subset=hospital["scope_results"]["code00_same_state_hospital_candidate"]
        n=subset["rows"]
        if n!=5362 or len(subset["services"])!=57 or len(subset["counts"])!=31:
            raise ValueError("QIES infrastructure scope mismatch")
        service_keys=("code_1","code_2","code_3","code_0","blank")
        service_counts={}
        for f,v in subset["services"].items():
            if set(v)-set(service_keys) or sum(v.values())!=n:raise ValueError("QIES service domain mismatch")
            service_counts[f]={k:v.get(k,0) for k in service_keys}
        count_states={}
        for f,v in subset["counts"].items():
            states=v["states"]
            if sum(states.values())!=n:raise ValueError("QIES count reconciliation")
            positive,zero=states.get("positive",0),states.get("zero",0)
            count_states[f]={"positive":positive,"zero":zero,"other_or_missing":n-positive-zero}
        ctx["qies_infra"]={"service_counts":service_counts,"count_states":count_states,
            "source_rows":hospital["source_rows"],"scope_rows":n,
            "comparison":hospital["public_hospital_comparison"],
            "scope_totals":{k:v["rows"] for k,v in hospital["scope_results"].items()}}
    semantic_path=ROOT/"research/clia_certificate_semantic_audit_20261126.json"
    if semantic_path.exists():
        ctx["clia_semantic"]=qualify_clia_semantic(read(semantic_path),ctx.get("clia_audit"),read(ROOT/"research/snapshot_release_20261125.json"))
    def resolve(cell):
        if isinstance(cell,dict):
            if set(cell)!={"path"}:raise ValueError("unexpected field selector")
            val=ctx
            for key in cell["path"]:val=val[key]
        else:val=cell
        if val is None or type(val) is int and val>=0 or isinstance(val,str) and len(val)<=300:return val
        raise ValueError("unexpected public cell type")
    result=[]
    for section in spec["sections"]:
        groups=[]
        for g in section["groups"]:
            groups.append({**{k:g[k] for k in ("id","title","note","run","columns","source")},"rows":[[resolve(c) for c in row] for row in g["rows"]]})
            if any(len(row)!=len(g["columns"]) for row in groups[-1]["rows"]):raise ValueError("table width")
        result.append({**{k:section[k] for k in ("id","title","intro")},"groups":groups})
    return {"version":1,"scope":"historical national aggregate qualification","sections":result}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--check",action="store_true")
    a=p.parse_args()
    obj=build(read(ROOT/"research/coverage_status.json"),read(ROOT/"research/public_capability_audit_20261126.json"),read(ROOT/"scripts/public_intelligence_spec.json"))
    out=ROOT/"web/public-intelligence.json"
    if a.check:
        if read(out)!=obj:raise SystemExit("Public intelligence projection differs from selected qualification evidence")
    else:out.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
if __name__=="__main__":main()
