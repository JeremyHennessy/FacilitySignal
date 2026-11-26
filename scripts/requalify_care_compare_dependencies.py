"""Requalify the narrow existing HHA service and LTCH capacity projections.

Use a byte-pinned publisher CSV, identical documented header inventory, exact
six-field institutional identity agreement and known source value domains.
Candidate files stay in the private preview workspace. No public writes.
"""
import copy,hashlib,json,re
from collections import Counter
from pathlib import Path
from build_combined import require,sha
import qualified_data_use as q
from restore_snapshot import fetch_missing,verify_raw

ROOT=Path(__file__).resolve().parents[1]
TARGETS={q.HHA,q.LTCH}
DEPENDENCIES={q.HHA:"home_health_service_evidence",q.LTCH:"long_term_hospital_capacity_enrichment"}
FIELDS=("ccn","name","address","city","state","zip")
KNOWN_HHA={"yes","no","dash_marker"}
KNOWN_LTCH={"reported_integer","dash_marker"}

def read(path):return json.loads(path.read_text())
def canonical(data):return (json.dumps(data,sort_keys=True,separators=(",",":"))+"\n").encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()

def load_headers():
    data=read(ROOT/"research/care_compare_pecos_exact_headers_20261126.json")
    headers={s["source"]:[f["field"] for f in s["fields"]] for s in data["sources"] if s["source"] in TARGETS}
    require(set(headers)==TARGETS and all(len(v)==len(set(v)) for v in headers.values()),"approved dependency header inventory")
    return headers

def hha_projection(shard,pin,rows,shard_sha):
    q.compare_directory(shard,pin,rows);counts={label:Counter() for label in q.SERVICES};records={}
    for r in shard["records"]:
        key=r["state"]+":"+r["ccn"]
        require(re.fullmatch(r"[A-Z]{2}:[A-Z0-9]{6}",key) is not None and key not in records,"HHA unique source identity")
        original=rows[(r["ccn"],r["state"])][0];v={}
        for label in q.SERVICES:
            state=q.classify(original["Offers "+label+" Services"],{"yes":"yes","no":"no"})
            require(state in KNOWN_HHA,"HHA service value domain changed")
            counts[label][state]+=1;v[label]=state
        records[key]=v
    require(len(records)==pin["stored_rows"] and all(sum(c.values())==len(records) for c in counts.values()),"HHA service coverage")
    payload={"format_version":1,"scope":"existing public home-health provider source records only","source":"care-compare-home-health","release":pin["release"],"source_sha256":pin["sha256"],"public_directory_sha256":shard_sha,"fields":list(q.SERVICES),"records":records}
    evidence={"dependency":DEPENDENCIES[q.HHA],"source_sha256":pin["sha256"],"source_release":pin["release"],"directory_sha256":shard_sha,"provider_records":len(records),"field_states":{label:dict(c) for label,c in counts.items()},"dictionary":q.DICT_HHA,"reuse":q.REUSE_HHA,"exact_identity_fields":list(FIELDS)}
    return canonical(payload),evidence

def ltch_projection(shard,pin,rows):
    q.compare_directory(shard,pin,rows);candidate=copy.deepcopy(shard);counts=Counter();values=[]
    for r in candidate["records"]:
        original=rows[(r["ccn"],r["state"])][0]
        capacity,state=q.quantity(original["Total Number of Beds"])
        require(state in KNOWN_LTCH,"LTCH capacity value domain changed")
        require(r["capacity"] in ("",capacity),"LTCH preexisting capacity disagrees")
        r["capacity"]=capacity;counts[state]+=1
        if state=="reported_integer":values.append(int(capacity))
    require(values and sum(counts.values())==len(rows)==pin["stored_rows"],"LTCH capacity count")
    data=q.json_bytes(candidate,compact=True)
    evidence={"dependency":DEPENDENCIES[q.LTCH],"source_sha256":pin["sha256"],"source_release":pin["release"],"source_field":"Total Number of Beds","unit":"reported total beds","rows":len(rows),"numeric_rows":len(values),"unknown_rows":len(rows)-len(values),"sum":sum(values),"min":min(values),"max":max(values),"zero":values.count(0),"value_states":dict(counts),"dictionary":q.DICT_LTCH,"reuse":q.REUSE_LTCH,"exact_identity_fields":list(FIELDS)}
    return data,evidence

def qualify(out,pins,changed,raw_root,approved,rehearse=False):
    selected=sorted(TARGETS if rehearse else TARGETS&set(changed))
    if not selected:return {}
    headers=load_headers();raw_root.mkdir()
    report={}
    directory=out/"web/public-directory"
    for key in selected:
        pin=pins[key];require(type(pin["bytes"]) is int and pin["bytes"]>0 and pin["input_rows"]==pin["stored_rows"],"dependency exact source byte/row pin")
        source=raw_root/(key+".csv");fetch_missing(pin,source)
        rows=q.source_rows(source,pin,headers[key])
        shard_path=directory/(key+".json");shard=read(shard_path)
        if key==q.HHA:
            data,evidence=hha_projection(shard,pin,rows,sha(shard_path))
            target=out/"web/hha-service-evidence.json"
            require(not target.exists(),"new HHA preview path")
            target.write_bytes(data)
            evidence["projection_sha256"]=sha(target)
            if rehearse:
                old=approved/"web/hha-service-evidence.json"
                require(sha(old)==sha(target),"approved HHA service byte parity")
                baseline=read(ROOT/"research/hha_service_public_audit_20261126.json")
                require(evidence["field_states"]==baseline["field_states"] and evidence["provider_records"]==baseline["provider_records"],"approved HHA field state parity")
        else:
            previous=sha(shard_path);data,evidence=ltch_projection(shard,pin,rows)
            shard_path.write_bytes(data);evidence["projection_sha256"]=sha(shard_path)
            manifest_path=directory/"manifest.json";manifest=read(manifest_path)
            if rehearse:
                baseline=read(ROOT/"research/qualified_data_use_20261126.json")["ltch"]
                require(previous==evidence["projection_sha256"]==sha(approved/"web/public-directory/long-term-hospital.json"),"approved LTCH capacity byte parity")
                require(evidence["numeric_rows"]==baseline["reported"] and evidence["unknown_rows"]==baseline["unknown"] and evidence["sum"]==baseline["sum"] and evidence["value_states"]==baseline["value_states"],"approved LTCH aggregate parity")
            else:
                require("long-term-hospital" not in manifest.get("field_enrichments",{}),"stale LTCH enrichment was not removed")
                manifest.setdefault("field_enrichments",{})[q.LTCH]={"source_sha256":evidence["source_sha256"],"release":evidence["source_release"],"source_field":evidence["source_field"],"unit":evidence["unit"],"projection_sha256":evidence["projection_sha256"],"prior_projection_sha256":previous,"numeric_rows":evidence["numeric_rows"],"unknown_rows":evidence["unknown_rows"],"sum":evidence["sum"],"dictionary":evidence["dictionary"],"reuse":evidence["reuse"],"method":"exact source CCN/state and six institutional identity fields; original public capacity column only"}
                manifest_path.write_bytes(q.json_bytes(manifest,compact=True))
        verify_raw(source,pin);source.unlink()
        evidence["status"]="BASELINE_PARITY_PASS" if rehearse else "PRIVATE_DEPENDENCY_QUALIFIED"
        evidence["public_promotion"]=False
        report[key]=evidence
    return report
