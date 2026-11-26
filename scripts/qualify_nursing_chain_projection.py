"""Qualify a narrow, release-scoped reported nursing chain membership candidate.

Only existing public provider CCN/state keys and CMS chain ID/member counts.
No chain names, owner names, contact information, PECOS joins or raw rows.
"""
import argparse,hashlib,json,re,sys,tempfile
from collections import Counter,defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qualified_data_use import source_rows,compare_directory
from restore_snapshot import LOCK,load_lock,materialize,verify_raw
ROOT=Path(__file__).resolve().parents[1]
PIN="ab70309ae6f0ee86b19fe9acb61a6d2953f970d3b09e80bb9b090e4b19ce35a2"
def require(ok,msg):
    if not ok:raise ValueError(msg)
def read(p):return json.loads(p.read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def qualify(shard,pin,rows):
    compare_directory(shard,pin,rows)
    membership={};groups=defaultdict(list);unknown=0
    for r in shard["records"]:
        k=(r["ccn"],r["state"]);identifier=k[1]+":"+k[0]
        require(re.fullmatch(r"[A-Z0-9]{6}",k[0]) is not None and re.fullmatch(r"[A-Z]{2}",k[1]) is not None,"Invalid provider key")
        raw=rows[k][0];token=raw["Chain ID"].strip();size=raw["Number of Facilities in Chain"].strip()
        if not token:
            require(not size and not raw["Chain Name"].strip(),"Blank group field conflict")
            unknown+=1;continue
        require(re.fullmatch(r"[0-9]{1,8}",token) is not None and re.fullmatch(r"[0-9]{1,5}",size) is not None and int(size)>0,"Unexpected chain field domain")
        name=" ".join(raw["Chain Name"].upper().split())
        require(bool(name),"Missing chain source name")
        membership[identifier]=token;groups[token].append((identifier,int(size),name))
    grouped={}
    for token,items in groups.items():
        sizes={i[1] for i in items};names={i[2] for i in items}
        require(sizes=={len(items)} and len(names)==1,"Unreconciled group membership")
        grouped[token]=len(items)
    require(len(membership)+unknown==len(shard["records"]) and sum(grouped.values())==len(membership),"Membership reconciliation")
    bands=Counter("1" if n==1 else "2-4" if n<=4 else "5-19" if n<=19 else "20-99" if n<=99 else "100+" for n in grouped.values())
    return membership,grouped,{"provider_records":len(shard["records"]),"reported_members":len(membership),"missing_group_records":unknown,"reported_group_count":len(grouped),"group_size_bands":dict(bands)}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--raw-dir",type=Path);p.add_argument("--download",action="store_true");p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    require(not a.out.exists(),"Output must be new")
    pin=next(s for s in load_lock(LOCK)["sources"] if s["key"]=="nursing")
    require(pin["sha256"]==PIN and pin["release"]=="2026-10-28" and pin["stored_rows"]==14686,"Source lock changed")
    baseline=next(x for x in read(ROOT/"research/nursing_semantic_audit_20261126.json")["audits"] if x["group"]=="chains")
    require(baseline["source_pins"]["nursing"]["sha256"]==PIN,"Prior qualification drift")
    headers={s["source"]:[f["field"] for f in s["fields"]] for s in read(ROOT/"research/care_compare_pecos_exact_headers_20261126.json")["sources"]}
    directory=(ROOT/"web/public-directory/nursing.json").read_bytes();shard=json.loads(directory)
    with tempfile.TemporaryDirectory(prefix="nursing-chain-projection-") as t:
        raw=materialize(pin,a.raw_dir,Path(t),a.download);rows=source_rows(raw,pin,headers["nursing"])
        membership,groups,audit=qualify(shard,pin,rows);verify_raw(raw,pin)
    previous=baseline["result"]
    require(audit["provider_records"]==previous["nursing"]["rows"]==14686 and audit["reported_members"]==previous["nursing"]["valid_chain_id"]==10227 and audit["missing_group_records"]==previous["nursing"]["blank_chain_id"]==4459 and audit["reported_group_count"]==previous["chains"]["groups"]==612 and audit["group_size_bands"]==previous["chains"]["observed_membership_size_bands"],"Prior exact group reconciliation mismatch")
    data={"format_version":1,"scope":"same-release reported CMS nursing chain membership only","source":"care-compare-nursing","release":pin["release"],"source_sha256":PIN,"public_directory_sha256":sha(directory),"memberships":membership,"groups":groups}
    body=(json.dumps(data,sort_keys=True,separators=(",",":"))+"\n").encode()
    audit.update({"source_release":pin["release"],"source_sha256":PIN,"public_directory_sha256":sha(directory),"payload_sha256":sha(body),"payload_bytes":len(body),"publication":"candidate_only","limits":"Publisher-defined group ID scoped to this source release. Blank is missing group evidence, not independent ownership. No names, owner or controlling-interest inference, property identity, current status, or PECOS identity merge."})
    a.out.mkdir(parents=True);(a.out/"nursing-chain-candidate.json").write_bytes(body);(a.out/"nursing-chain-audit.json").write_text(json.dumps(audit,indent=2)+"\n")
    print("NURSING_CHAIN_PROJECTION_PASS",json.dumps(audit,sort_keys=True),flush=True)
if __name__=="__main__":main()
