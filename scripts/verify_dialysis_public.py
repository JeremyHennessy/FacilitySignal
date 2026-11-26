"""Verify/install the exact narrow public-use dialysis projection. No source downloads."""
import argparse,hashlib,json,shutil
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PAYLOAD="9617a05946fc165416c1c69c937eaeb4d82f29871bd7f04a88413664c80cb738"
AUDIT="a7bfd44c4ccfc310d3f8f0e03ce599bef15b715a8b29c2566b1fdcf429c044cc"
PROVIDER="e8343f678ec1780ac49047f162754657f60eaa3f61b1d4f48ea4b55d39d4008a"
SOURCE="50b3fd74d88e08d2eaaf60e11a9230175acae0045b9fe9f803b91be8b8359dd2"
DICTIONARY="bd68d76dc72ee5c3b3249c459644ff2ed90c8e8cf6e182b76742ec53164c0594"
FIELDS={"dlys_stn_cnt","hmdlys_srvc_sw","prtnl_dlys_srvc_sw","home_trng_sprt_only_srvc_sw"}
def read(path,digest):
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError("Pinned checksum mismatch: "+str(path))
    return json.loads(raw)
def require(ok,msg):
    if not ok:raise ValueError(msg)
def verify(payload_path,audit_path):
    p=read(payload_path,PAYLOAD);a=read(audit_path,AUDIT)
    d=read(ROOT/"web/public-directory/dialysis.json",PROVIDER)
    require(d["source"]=="dialysis" and len(d["records"])==d["row_count"]==7471,"Directory coverage mismatch")
    ids={r["ccn"] for r in d["records"]}
    require(len(ids)==7471 and set(p)=={"format_version","scope","registry","period","source_sha256","dictionary_sha256","public_dialysis_sha256","records","fields"},"Public projection schema")
    require(p["format_version"]==1 and p["registry"]=="iqies" and p["period"]=="2026-07-01/2026-09-30" and p["source_sha256"]==SOURCE and p["dictionary_sha256"]==DICTIONARY and p["public_dialysis_sha256"]==PROVIDER,"Source lineage mismatch")
    require(set(p["fields"])==FIELDS and len(p["records"])==2194 and set(p["records"])<=ids,"Candidate scope mismatch")
    counts={f:Counter() for f in FIELDS}
    for ident,obs in p["records"].items():
        require(set(obs)==FIELDS,"Observation field scope")
        for f,v in obs.items():
            counts[f][v["state"]]+=1
            if f=="dlys_stn_cnt":require(set(v)=={"state","count"} and (type(v["count"]) is int and v["count"]>=0 if v["state"]=="reported_count" else v["state"]=="not_available" and v["count"] is None),"Invalid count observation")
            else:require(set(v)=={"state"} and v["state"] in {"reported_yes","reported_no","not_available"},"Invalid indicator observation")
    require({f:dict(c) for f,c in counts.items()}==a["corroborated_field_states"],"Field reconciliation")
    require(a["payload_sha256"]==PAYLOAD and a["payload_bytes"]==payload_path.stat().st_size and a["public_dialysis_sha256"]==PROVIDER and a["source_sha256"]==SOURCE,"Audit lineage")
    require(a["match_dispositions"]=={"address_evidence_disagrees":5262,"corroborated":2194,"no_esrd_identifier_candidate":15},"Candidate disposition mismatch")
    print("DIALYSIS_PUBLIC_PROJECTION_VERIFIED",len(p["records"]),len(ids),PAYLOAD)
def main():
    parser=argparse.ArgumentParser();parser.add_argument("--install",type=Path);a=parser.parse_args()
    target=ROOT/"web/dialysis-service-evidence.json";audit=ROOT/"research/dialysis_service_public_audit_20261126.json"
    if a.install:
        src=a.install/"dialysis-service-candidate.json";aud=a.install/"dialysis-service-audit.json"
        verify(src,aud);shutil.copyfile(src,target);shutil.copyfile(aud,audit)
    verify(target,audit)
if __name__=="__main__":main()
