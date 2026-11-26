"""Install/verify exact qualified same-source home health service projection."""
import argparse,hashlib,json,shutil
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
PAYLOAD="88dd0b1a9db445c8c5b33ad09225ed86a9a9c516ad6be3c259f035a3e06263e1"
AUDIT="71992451851177705666f7b16623e8dd205a10dd91990cb223ea563aefbff300"
PROVIDER="3b244338ff11e39258aa0620a4b3a6f1813c6b8569f0290380f06493e0344d3d"
SOURCE="7adf3e17961949bbd64ef243545aa387224d9837e8c5601476f5b11946e76d22"
FIELDS=["Nursing Care","Physical Therapy","Occupational Therapy","Speech Pathology","Medical Social","Home Health Aide"]
def read(path,digest):
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError("Pinned checksum mismatch: "+str(path))
    return json.loads(raw)
def require(ok,msg):
    if not ok:raise ValueError(msg)
def verify(payload_path,audit_path):
    p=read(payload_path,PAYLOAD);a=read(audit_path,AUDIT);d=read(ROOT/"web/public-directory/home-health.json",PROVIDER)
    require(d["source"]=="home-health" and d["release"]=="2026-10-21" and len(d["records"])==d["row_count"]==12409,"Directory mismatch")
    ids={r["state"]+":"+r["ccn"] for r in d["records"]}
    require(len(ids)==12409 and set(p)=={"format_version","scope","source","release","source_sha256","public_directory_sha256","fields","records"},"Schema mismatch")
    require(p["format_version"]==1 and p["source"]=="care-compare-home-health" and p["release"]==d["release"] and p["source_sha256"]==SOURCE and p["public_directory_sha256"]==PROVIDER,"Source lineage mismatch")
    require(p["fields"]==FIELDS and set(p["records"])==ids,"Public identity coverage mismatch")
    counts={f:Counter() for f in FIELDS}
    for obs in p["records"].values():
        require(set(obs)==set(FIELDS),"Unexpected service fields")
        for f,v in obs.items():
            require(v in {"yes","no","dash_marker"},"Invalid evidence state");counts[f][v]+=1
    require({f:dict(c) for f,c in counts.items()}==a["field_states"],"Field reconciliation")
    require(a["payload_sha256"]==PAYLOAD and a["payload_bytes"]==payload_path.stat().st_size and a["public_directory_sha256"]==PROVIDER and a["source_sha256"]==SOURCE and a["provider_records"]==12409,"Audit lineage mismatch")
    print("HHA_PUBLIC_PROJECTION_VERIFIED",len(ids),PAYLOAD)
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--install",type=Path);a=parser.parse_args()
    target=ROOT/"web/hha-service-evidence.json";audit=ROOT/"research/hha_service_public_audit_20261126.json"
    if a.install:
        src=a.install/"hha-service-candidate.json";aud=a.install/"hha-service-audit.json"
        verify(src,aud);shutil.copyfile(src,target);shutil.copyfile(aud,audit)
    verify(target,audit)
if __name__=="__main__":main()
