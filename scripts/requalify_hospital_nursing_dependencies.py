"""Requalify historical hospital and nursing aggregate evidence for release preview.

Only pinned source files and the selected verified institutional directory are
used. Reuse the exact original audit algorithms; preserve approved baseline
evidence and source/dictionary limitations. Retain aggregate receipts only.
"""
import hashlib,json,tempfile
from collections import Counter,defaultdict
from contextlib import closing
from datetime import date
from pathlib import Path
from build_combined import require,sha,readonly
from restore_snapshot import fetch_missing,verify_raw
from qualified_data_use import source_rows,compare_directory
import qies_infrastructure_audit as hospital
import hospital_lab_corroboration as lab
import clia_domain_link_audit as clia
import nursing_semantic_audit as nursing
import citation_evidence as citations
from institutional_observations import RULES
ROOT=Path(__file__).resolve().parents[1]
BASELINE={
 "nursing_semantic_audit_20261126.json":"39cdde371d049201f935cbf286a0a35d068e34e2",
 "care_compare_infrastructure_qualification_20261126.json":"bd5a81a1fd6b8f77dd5ca282873dfab8c9ad542c",
 "qies_hospital_infrastructure_audit_20261126.json":"02d8073510b3e7945a80f2d283a01e762ee98143",
 "hospital_lab_corroboration_qualification_20261126.json":"46f5bbf752786c421f8d09fbfd260905c5afbbe0",
}
def read(path):return json.loads(path.read_text())
def pinned_baseline(name):
    raw=(ROOT/"research"/name).read_bytes()
    git=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    require(git==BASELINE[name],"reviewed aggregate baseline blob changed")
    return json.loads(raw)
def registry_ready(report,keys,rehearse):
    if rehearse:return True
    states=(report or {}).get("sources",{}).get("registry_and_ownership",{})
    return all(states.get(k,{}).get("state")=="unchanged" for k in keys)
def block(dependency,reason):
    return {"dependency":dependency,"status":"SOURCE_REVIEW_REQUIRED","reason":reason,"public_promotion":False}
def pin_meta(pin):return {"release":pin["release"],"sha256":pin["sha256"],"rows":pin["stored_rows"]}
def exact_source(root,key,pin):
    target=root/(key+".csv");require(not target.exists(),"new dependency source path")
    fetch_missing(pin,target);verify_raw(target,pin);return target
def public_records(out,key,pin):
    p=out/"web/public-directory"/(key+".json");shard=read(p)
    require(shard["source"]==key and shard["release"]==pin["release"] and shard["row_count"]==len(shard["records"])==pin["stored_rows"],"selected directory scope")
    keys={(r["ccn"],r["state"]) for r in shard["records"]}
    require(len(keys)==len(shard["records"]),"selected directory identity uniqueness")
    return p,shard,keys
def qualified(dependency,source_pins,result,rehearse):
    return {"dependency":dependency,"status":"BASELINE_PARITY_PASS" if rehearse else "PRIVATE_DEPENDENCY_QUALIFIED","source_pins":source_pins,"aggregate_result":result,"public_promotion":False}

def nursing_provider(out,pins,registry_pins,headers,root,rehearse,report):
    dep="nursing_provider_and_chain_evidence"
    if not registry_ready(report,["snf-enrollment"],rehearse):return block(dep,"SNF enrollment publisher version is not qualified as unchanged")
    pin=pins["nursing"];enroll=registry_pins["snf-enrollment"]
    if pin["input_rows"]!=pin["stored_rows"]:return block(dep,"nursing duplicate source row policy requires review")
    source=exact_source(root,"nursing",pin);enrollment=exact_source(root,"snf-enrollment",enroll)
    path,shard,_=public_records(out,"nursing",pin)
    raw=source_rows(source,pin,headers["nursing"]);compare_directory(shard,pin,raw)
    # Exact known literal provider domains; a new marker cannot silently
    # become a clinical or regulatory classification.
    literals={rule[0]:Counter() for rule in RULES["nursing"].values()}
    for row,_ in raw.values():
        for _,(field,domain,_) in RULES["nursing"].items():
            v=row[field];require(v in domain,"nursing provider literal domain changed")
            literals[field][v if v else "<blank>"]+=1
    require(all(sum(c.values())==pin["stored_rows"] for c in literals.values()),"nursing provider fields count")
    result=nursing.chain_audit((row for row,_ in raw.values()),nursing.records(enrollment,enroll,headers["snf-enrollment"]))
    require(result["nursing"].get("unrecognized_chain_id",0)==0 and result["snf_enrollment"].get("unrecognized_affiliation_id",0)==0,"new chain/affiliation identifier domain")
    provider={k:dict(v) for k,v in literals.items()}
    if rehearse:
        prior=next(x["result"] for x in pinned_baseline("nursing_semantic_audit_20261126.json")["audits"] if x["group"]=="chains")
        require(result==prior,"approved nursing chain aggregate parity")
        prior_provider=pinned_baseline("care_compare_infrastructure_qualification_20261126.json")["sources"]["nursing"]
        require(provider==prior_provider["literal_counts"],"approved nursing provider aggregate parity")
    verify_raw(source,pin);verify_raw(enrollment,enroll);source.unlink();enrollment.unlink()
    return qualified(dep,{"nursing":{**pin_meta(pin),"directory_sha256":sha(path)},"snf-enrollment":pin_meta(enroll)},{"provider_literal_counts":provider,"chain_evidence":result},rehearse)

def normalized_citation(db_path,key,pin,provider_keys):
    release=date.fromisoformat(pin["release"]);counts=defaultdict(Counter);n=0;unmapped=set()
    with closing(readonly(db_path)) as db:
        observed=db.execute("SELECT r.id,r.sha256,r.published_on,r.stored_rows FROM current_release c JOIN releases r ON c.release_id=r.id WHERE c.dataset=?",(key,)).fetchone()
        require(observed is not None and observed[1:]==(pin["sha256"],pin["release"],pin["stored_rows"]),"normalized citation release lineage")
        for ccn,state,tag,status,correction,survey,rid in db.execute("SELECT ccn,state,tag,correction_status,correction_date,survey_date,release_id FROM findings WHERE dataset=?",(key,)):
            require(rid==observed[0],"normalized citation source release")
            e=citations.evidence(key,tag,status,correction,survey,release,(ccn,state) in provider_keys)
            if e["resolution_state"]=="unmapped":unmapped.add(status)
            require(e.pop("confirmed_opportunity") is False,"citation inference scope")
            for k,v in e.items():counts[k][v]+=1
            n+=1
    require(n==pin["stored_rows"] and all(sum(c.values())==n for c in counts.values()),"normalized citation row reconciliation")
    return {"rows":n,"distributions":{k:dict(v) for k,v in counts.items()},"distinct_unmapped_correction_values":len(unmapped),"confirmed_opportunities":0}

def nursing_citations(out,pins,changed,base_db,candidates,headers,root,rehearse):
    output={};path,_,provider_keys=public_records(out,"nursing",pins["nursing"])
    old=next(x["result"] for x in pinned_baseline("nursing_semantic_audit_20261126.json")["audits"] if x["group"]=="citations")
    for key in ("nursing-health","nursing-fire"):
        if not rehearse and key not in changed and "nursing" not in changed:continue
        dep="nursing_"+key.removeprefix("nursing-")+"_citation_evidence";pin=pins[key]
        if pin["input_rows"]!=pin["stored_rows"]:
            output[key]=block(dep,"duplicate source citations require an explicit flag-to-normalized row reconciliation");continue
        source=exact_source(root,key,pin)
        stats=nursing.citation(nursing.records(source,pin,headers[key]),key=="nursing-fire")
        require(stats["rows"]==pin["stored_rows"] and all(set(c)<={"yes","no"} for c in stats["flags"].values()) and set(stats["inspection_cycle_codes"])<={"1","2","3"},"nursing citation literal domain changed")
        if key=="nursing-fire":require(set(stats["tag_version"])<={"new","old"},"fire tag version domain changed")
        norm=normalized_citation(candidates.get(key,base_db),key,pin,provider_keys)
        require(norm["rows"]==stats["rows"],"normalized and raw citation count agreement")
        if rehearse:
            require(stats==old[key],"approved citation flag aggregate parity")
            require(norm["distributions"]["provider_linkage"]=={"same_ccn_state_provider_record":pin["stored_rows"]},"approved citation linkage parity")
        verify_raw(source,pin);source.unlink()
        output[key]=qualified(dep,{key:pin_meta(pin),"nursing":{**pin_meta(pins["nursing"]),"directory_sha256":sha(path)}},{"raw_citation_evidence":stats,"normalized_citation_evidence":norm},rehearse)
    if rehearse:
        norm=[v["aggregate_result"]["normalized_citation_evidence"] for v in output.values()]
        prior=read(ROOT/"research/coverage_status.json")["citation_evidence_qualified_baseline"]
        require(sum(v["rows"] for v in norm)==prior["citation_rows"] and sum(v["distributions"]["resolution_state"].get("unmapped",0) for v in norm)==prior["unmapped_correction_rows"] and sum(v["distributions"]["correction_date_state"].get("after_release",0) for v in norm)==prior["correction_dates_after_release"],"approved combined citation evidence parity")
    return output

def reviewed_hospital_catalog(prior,qpin):
    require(prior["qualification_run"]==45829855217 and prior["source_sha256"]==qpin["sha256"] and prior["historical_layout_sha256"]==hospital.LAYOUT_SHA and prior["historical_layout_artifact_sha256"]==hospital.ARTIFACT_SHA,"reviewed hospital dictionary lineage")
    exact={k:{f:v[f] for f in ("label","definition","page","printed_page","codes")} for k,v in prior["catalog"].items()}
    exact[prior["blocked_field"]["field"]]=prior["blocked_field"]["historical_reference"]
    svc={k:exact[k] for k in prior["scope_results"]["all"]["services"]}
    fte={k:exact[k] for k in prior["scope_results"]["all"]["fte"]}
    require(len(svc)==57 and len(fte)==20 and set(hospital.COUNTS+hospital.FLAGS+hospital.STATUS+("OPRTG_ROOM_CNT",))<=set(exact),"reviewed catalog scope")
    return exact,svc,fte

def hospital_evidence(out,pins,registry_pins,root,rehearse,report):
    dep="hospital_infrastructure_and_laboratory_evidence"
    if not registry_ready(report,["qies","clia"],rehearse):return block(dep,"QIES or CLIA publisher version is not qualified as unchanged")
    pin=pins["hospital"];qpin=registry_pins["qies"];cpin=registry_pins["clia"]
    prior=pinned_baseline("qies_hospital_infrastructure_audit_20261126.json")
    prior_lab=pinned_baseline("hospital_lab_corroboration_qualification_20261126.json")
    require(prior_lab["source_hashes"]=={"qies":qpin["sha256"],"clia":cpin["sha256"]},"reviewed lab source lineage")
    path,shard,_=public_records(out,"hospital",pin);public=defaultdict(list)
    for r in shard["records"]:public[r["ccn"]].append(r)
    meta={"sha256":sha(path),"release":pin["release"],"records":pin["stored_rows"]}
    inv=read(hospital.INVENTORY)["registries"]
    raw=exact_source(root,"qies",qpin);labs=exact_source(root,"clia",cpin)
    expected=read(ROOT/"research/public_capability_audit_20261126.json")["qies_field_distributions"]
    result=hospital.audit(raw,qpin,inv["qies"],None,public,meta,expected,reviewed_catalog=reviewed_hospital_catalog(prior,qpin))
    l=lab.audit(clia.stream(raw,qpin,inv["qies"]),clia.stream(labs,cpin,inv["clia"]),public)
    require(sum(l["hospital_cohorts"].values())==qpin["stored_rows"] and l["lab_rows"]==cpin["stored_rows"],"hospital/lab source count")
    if rehearse:
        require(all(result[k]==prior[k] for k in result),"approved QIES infrastructure aggregate parity")
        require(l==prior_lab["result"] and meta==prior_lab["public_hospital"],"approved laboratory aggregate parity")
    verify_raw(raw,qpin);verify_raw(labs,cpin);raw.unlink();labs.unlink()
    # The detailed aggregate is source-scoped historical data. Keep it in
    # the private receipt, not a public pack or row-level relationship.
    return qualified(dep,{"hospital":{**pin_meta(pin),"directory_sha256":meta["sha256"]},"qies":pin_meta(qpin),"clia":pin_meta(cpin)},{"infrastructure":result,"laboratory":l},rehearse)

def qualify(out,pins,changed,base_db,candidates,root,rehearse=False,report=None):
    targets={"hospital","nursing","nursing-health","nursing-fire"}
    if not rehearse and not targets&set(changed):return {}
    root.mkdir();lock=read(ROOT/"research/snapshot_release_20261125.json")
    registry_pins={p["key"]:p for p in lock["sources"] if p["key"] in ("qies","clia","snf-enrollment")}
    headers={s["source"]:[f["field"] for f in s["fields"]] for s in read(ROOT/"research/care_compare_pecos_exact_headers_20261126.json")["sources"]}
    output={}
    if rehearse or "nursing" in changed:output["nursing-provider"]=nursing_provider(out,pins,registry_pins,headers,root,rehearse,report)
    output.update(nursing_citations(out,pins,changed,base_db,candidates,headers,root,rehearse))
    if rehearse or "hospital" in changed:output["hospital"]=hospital_evidence(out,pins,registry_pins,root,rehearse,report)
    return output
