"""Qualify a minimal dialysis capability projection against existing public providers.

No new identifying fields are published. The only join key is an existing public
Care Compare CCN. All raw registry rows and address comparison values are ephemeral.
"""
import argparse,csv,hashlib,json,re,sys,tempfile
from collections import Counter,defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from restore_snapshot import LOCK,load_lock,materialize,verify_raw
from collect_registry import open_csv,source_encoding
from iqies_capabilities import load_dictionary,normalize_code,normalize_value,RULES
from probe_iqies_dictionary import download as download_dictionary,URL as DICTIONARY_URL
from probe_pos_fields import INVENTORY
ROOT=Path(__file__).resolve().parents[1]
FIELDS=tuple(k for k,v in RULES.items() if v[0]=="ESRD")
STATES=set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR VI".split())
def require(ok,msg):
    if not ok:raise ValueError(msg)
def norm(v):return " ".join(str(v or "").casefold().split())
def zip5(v):
    s=str(v or "").strip()
    return s[:5] if re.fullmatch(r"[0-9]{5}(?:-?[0-9]{4})?",s) else ""
def corroboration(public,source):
    if source["state_cd"].strip()!=public["state"]:return "state_conflict_or_missing"
    pairs=[(norm(public["address"]),norm(source["st_adr"])),(norm(public["city"]),norm(source["city_name"])),(zip5(public["zip"]),zip5(source["zip_cd"]))]
    if any(not a or not b for a,b in pairs):return "incomplete_address_evidence"
    return "corroborated" if all(a==b for a,b in pairs) else "address_evidence_disagrees"
def qualify(rows,public,scopes,expected_states=None,expected_rows=None):
    # No identity fields from the registry survive this function.
    by_id=defaultdict(list);scope_count=0;seen=0;field_states=defaultdict(Counter);count_sum=0
    for row in rows:
        seen+=1
        require(None not in row and all(v is not None for v in row.values()),"Malformed registry record")
        if scopes.get(normalize_code(row["prvdr_type_id"]))!="ESRD":continue
        scope_count+=1
        values={}
        for field in FIELDS:
            state,value=normalize_value(row[field],RULES[field][1])
            field_states[field][state]+=1
            if field=="dlys_stn_cnt" and value is not None:count_sum+=value
            values[field]={"state":state,"count":value} if RULES[field][1]=="count" else {"state":state}
        ident=row["prvdr_num"].strip()
        if ident in public:
            by_id[ident].append((corroboration(public[ident],row),values))
    if expected_rows is not None:require(seen==expected_rows and scope_count==8659,"Registry/source scope count changed")
    if expected_states is not None:
        for field in FIELDS:
            expected={k:v for k,v in expected_states[field].items() if v is not None}
            require(dict(field_states[field])==expected,"Qualified field state reconciliation failed: "+field)
        require(count_sum==134626,"Approved station sum drift")
    dispositions=Counter();records={};subset_states=defaultdict(Counter)
    for ident in sorted(public):
        hits=by_id.get(ident,[])
        if not hits:dispositions["no_esrd_identifier_candidate"]+=1;continue
        if len(hits)!=1:dispositions["multiple_esrd_identifier_candidates"]+=1;continue
        status,values=hits[0];dispositions[status]+=1
        if status!="corroborated":continue
        records[ident]=values
        for field,value in values.items():subset_states[field][value["state"]]+=1
    require(sum(dispositions.values())==len(public) and len(records)==dispositions["corroborated"],"Public provider coverage mismatch")
    return records,{"registry_rows":seen,"esrd_source_rows":scope_count,"public_dialysis_rows":len(public),"match_dispositions":dict(dispositions),"published_candidate_rows":len(records),"all_esrd_field_states":{k:dict(v) for k,v in field_states.items()},"corroborated_field_states":{k:dict(v) for k,v in subset_states.items()},"all_esrd_approved_station_count_sum":count_sum}
def load_public():
    path=ROOT/"web/public-directory/dialysis.json";raw=path.read_bytes();d=json.loads(raw)
    manifest=json.loads((path.parent/"manifest.json").read_text())
    require(d["source"]=="dialysis" and d["release"]=="2026-10-28" and len(d["records"])==d["row_count"]==manifest["sources"]["dialysis"]["published_records"]==7471,"Public baseline changed")
    result={}
    for row in d["records"]:
        ident=row["ccn"]
        require(re.fullmatch(r"[A-Z0-9]{6}",ident) is not None and ident not in result and row["state"] in STATES,"Public provider identifier gate")
        result[ident]=row
    return result,hashlib.sha256(raw).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--out",type=Path,required=True);p.add_argument("--raw-dir",type=Path);p.add_argument("--dictionary",type=Path);p.add_argument("--download",action="store_true")
    a=p.parse_args();require(not a.out.exists(),"Output must be new")
    item=next(s for s in load_lock(LOCK)["sources"] if s["key"]=="iqies")
    require(item["metadata"]["license"]=="https://www.usa.gov/government-works" and item["release"]=="2026-07-01/2026-09-30","Publisher reuse/period pin changed")
    public,digest=load_public()
    audit_pin=json.loads((ROOT/"research/public_capability_audit_20261126.json").read_text())
    with tempfile.TemporaryDirectory(prefix="dialysis-service-") as temp:
        stage=Path(temp)
        raw=materialize(item,a.raw_dir,stage,a.download)
        dic=a.dictionary or stage/"dictionary.xlsx"
        if not a.dictionary:
            require(a.download,"Explicit download required for dictionary")
            download_dictionary(dic)
        _,codes,scopes=load_dictionary(dic)
        expected=[x["field"] for x in json.loads(INVENTORY.read_text())["registries"]["iqies"]["fields"]]
        with open_csv(raw,item["metadata"]["zipped"],source_encoding(raw,item["metadata"]["zipped"])) as source:
            reader=csv.DictReader(source,strict=True);require(reader.fieldnames==expected,"Pinned registry schema changed")
            records,audit=qualify(reader,public,scopes,audit_pin["iqies_field_states"],item["input_rows"])
        verify_raw(raw,item)
    require(audit["published_candidate_rows"]>0,"No sufficiently corroborated records")
    # Only keys already present in the public dialysis file and four qualified observations.
    payload={"format_version":1,"scope":"corroborated existing public dialysis provider records only","registry":"iqies","period":item["release"],"source_sha256":item["sha256"],"public_dialysis_sha256":digest,"dictionary_sha256":hashlib.sha256(dic.read_bytes()).hexdigest() if a.dictionary else "bd68d76dc72ee5c3b3249c459644ff2ed90c8e8cf6e182b76742ec53164c0594","records":records,"fields":{k:{"label":RULES[k][2],"kind":RULES[k][1]} for k in FIELDS}}
    encoded=(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n").encode()
    audit.update({"payload_bytes":len(encoded),"payload_sha256":hashlib.sha256(encoded).hexdigest(),"source_sha256":item["sha256"],"source_period":item["release"],"dictionary":DICTIONARY_URL,"public_dialysis_sha256":digest,"reuse_evidence":"Q3 2026 CMS POS public use file; version catalog government works license; selected institutional service fields only. No new identity/contact fields.","status":"candidate_qualified_not_deployed","limits":"Exact CCN + single ESRD candidate + state/address/city/ZIP text corroboration; not canonical site, equipment or current operation. Missing candidate not zero/no. Approved in-center stations differ from Care Compare station counts; never add."})
    a.out.mkdir(parents=True)
    (a.out/"dialysis-service-candidate.json").write_bytes(encoded)
    (a.out/"dialysis-service-audit.json").write_text(json.dumps(audit,indent=2)+"\n")
    print("DIALYSIS_SERVICE_QUALIFICATION",json.dumps(audit,sort_keys=True),flush=True)
if __name__=="__main__":main()
