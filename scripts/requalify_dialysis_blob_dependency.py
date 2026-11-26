"""Rebuild narrow dialysis evidence using the verified national iQIES Blob DB.

Reuse only qualified, dictionary-pinned ESRD observations and the six-field
Care Compare institutional identity projection. No raw registry identity fields
survive the scratch computation. Require exact historical baseline parity.
"""
import json,re
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path
from build_combined import require,sha,readonly
from iqies_capabilities import RULES,DICT_SHA
from scripts.qualify_dialysis_service_projection import corroboration,STATES
ROOT=Path(__file__).resolve().parents[1]
FIELDS=tuple(k for k,v in RULES.items() if v[0]=="ESRD")
DEPENDENCY="dialysis_registry_corroboration"
MAPPING={"provider_id":"prvdr_num","address":"st_adr","city":"city_name","state":"state_cd","zip":"zip_cd"}
def read(path):return json.loads(path.read_text())

def selected_registry_rows(db,item,prior):
    release=db.execute("SELECT source_sha256,row_count,period,column_mapping FROM certification_releases WHERE registry='iqies'").fetchone()
    require(release is not None and tuple(release[:3])==(item["sha256"],item["stored_rows"],item["release"]),"iQIES registry release identity")
    mapping=json.loads(release[3]);require(all(mapping.get(k)==v for k,v in MAPPING.items()),"iQIES identity mapping changed")
    capability=db.execute("SELECT source_sha256,dictionary_sha256,source_period,source_rows FROM iqies_capability_release WHERE singleton=1").fetchone()
    require(capability==(item["sha256"],DICT_SHA,item["release"],item["input_rows"]),"iQIES capability dictionary and source lineage")
    require(db.execute("SELECT count(*) FROM certification_records WHERE registry='iqies'").fetchone()[0]==item["stored_rows"]==item["input_rows"],"iQIES source count")
    require(item["metadata"]["license"]=="https://www.usa.gov/government-works","registry reuse pin")
    grouped={};states={f:Counter() for f in FIELDS};station_sum=0
    rows=db.execute("""SELECT r.row_number,r.provider_id,r.state,r.address,r.city,r.zip,o.field,o.value_state,o.count_value
        FROM certification_records r JOIN iqies_capability_observations o ON o.registry=r.registry AND o.row_number=r.row_number
        WHERE r.registry='iqies' AND o.provider_scope='ESRD' ORDER BY r.row_number,o.field""")
    for ordinal,ident,state,address,city,zip_code,field,value,count in rows:
        require(field in FIELDS,"unexpected ESRD field")
        identity={"prvdr_num":ident,"state_cd":state,"st_adr":address,"city_name":city,"zip_cd":zip_code}
        existing=grouped.setdefault(ordinal,(identity,{}))
        require(existing[0]==identity and field not in existing[1],"ESRD row or field duplication")
        if RULES[field][1]=="count":
            require((value=="reported_count" and type(count) is int and count>=0) or (value=="not_available" and count is None),"ESRD count domain")
            existing[1][field]={"state":value,"count":count}
            if count is not None:station_sum+=count
        else:
            require(value in {"reported_yes","reported_no","not_available"} and count is None,"ESRD flag domain")
            existing[1][field]={"state":value}
        states[field][value]+=1
    require(len(grouped)==prior["esrd_source_rows"] and all(set(v[1])==set(FIELDS) for v in grouped.values()),"ESRD observation row scope")
    require({k:dict(v) for k,v in states.items()}==prior["all_esrd_field_states"] and station_sum==prior["all_esrd_approved_station_count_sum"],"ESRD baseline aggregate drift")
    return list(grouped.values())

def project(shard,pin,registry_rows):
    require(shard["source"]=="dialysis" and shard["release"]==pin["release"] and shard["row_count"]==len(shard["records"])==pin["stored_rows"],"dialysis directory release/count")
    public={}
    for row in shard["records"]:
        ident=row["ccn"]
        require(set(row)=={"ccn","name","address","city","state","zip","capacity"} and re.fullmatch(r"[A-Z0-9]{6}",ident) and ident not in public and row["state"] in STATES,"dialysis institutional directory scope")
        public[ident]=row
    by_id=defaultdict(list)
    for identity,values in registry_rows:
        ident=identity["prvdr_num"].strip()
        if ident in public:by_id[ident].append((corroboration(public[ident],identity),values))
    records={};dispositions=Counter();states={f:Counter() for f in FIELDS}
    for ident in sorted(public):
        hits=by_id.get(ident,[])
        if not hits:dispositions["no_esrd_identifier_candidate"]+=1;continue
        if len(hits)!=1:dispositions["multiple_esrd_identifier_candidates"]+=1;continue
        status,values=hits[0];dispositions[status]+=1
        if status!="corroborated":continue
        records[ident]=values
        for field,value in values.items():states[field][value["state"]]+=1
    require(len(public)==sum(dispositions.values()) and len(records)==dispositions["corroborated"] and all(sum(v.values())==len(records) for v in states.values()),"dialysis candidate reconciliation")
    require(records,"no exact corroborated dialysis providers")
    return records,{"public_dialysis_rows":len(public),"match_dispositions":dict(dispositions),"published_candidate_rows":len(records),"corroborated_field_states":{f:dict(v) for f,v in states.items()}}

def qualify(out,pins,changed,base_db,approved,weekly_report,rehearse=False):
    if not rehearse and "dialysis" not in changed:return None
    # A newly reported registry version is not silently treated as the reviewed
    # historical iQIES source. It must be independently qualified first.
    if not rehearse:
        state=(weekly_report or {}).get("sources",{}).get("registry_and_ownership",{}).get("iqies",{}).get("state")
        if state!="unchanged":return {"dependency":DEPENDENCY,"status":"REGISTRY_REVIEW_REQUIRED","registry_metadata_state":state or "not_checked","public_promotion":False}
    lock=read(ROOT/"research/snapshot_release_20261125.json");item=next(s for s in lock["sources"] if s["key"]=="iqies")
    prior=read(ROOT/"research/dialysis_service_public_audit_20261126.json")
    require(item["sha256"]==prior["source_sha256"] and item["release"]==prior["source_period"],"approved registry audit pin")
    with closing(readonly(base_db)) as db:rows=selected_registry_rows(db,item,prior)
    shard=out/"web/public-directory/dialysis.json";records,stats=project(read(shard),pins["dialysis"],rows)
    payload={"format_version":1,"scope":"corroborated existing public dialysis provider records only","registry":"iqies","period":item["release"],"source_sha256":item["sha256"],"public_dialysis_sha256":sha(shard),"dictionary_sha256":DICT_SHA,"records":records,"fields":{k:{"label":RULES[k][2],"kind":RULES[k][1]} for k in FIELDS}}
    target=out/"web/dialysis-service-evidence.json";require(not target.exists(),"new private dialysis dependency path")
    target.write_bytes((json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n").encode())
    digest=sha(target)
    if rehearse:
        require(digest==prior["payload_sha256"]==sha(approved/"web/dialysis-service-evidence.json"),"approved dialysis payload byte parity")
        require(all(stats[k]==prior[k] for k in stats),"approved dialysis match/field state parity")
    return {**stats,"dependency":DEPENDENCY,"status":"BASELINE_PARITY_PASS" if rehearse else "PRIVATE_DEPENDENCY_QUALIFIED","registry_source_sha256":item["sha256"],"registry_period":item["release"],"registry_database_sha256":sha(base_db),"dictionary_sha256":DICT_SHA,"public_dialysis_sha256":sha(shard),"projection_sha256":digest,"public_promotion":False}
