"""Qualify an institutional home-health service projection from the exact public Care Compare release.

Only existing public source identifiers and six source-native service indicators.
No contact, patient, quality measure, owner, or individual record identifiers.
"""
import argparse,hashlib,json,re,sys,tempfile
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qualified_data_use import source_rows,compare_directory,classify,SERVICES,DICT_HHA,REUSE_HHA
from restore_snapshot import LOCK,load_lock,materialize,verify_raw
ROOT=Path(__file__).resolve().parents[1]
SOURCE_SHA="7adf3e17961949bbd64ef243545aa387224d9837e8c5601476f5b11946e76d22"
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(p):return json.loads(p.read_text())
def qualify(shard,pin,rows,expected):
    compare_directory(shard,pin,rows)
    counts={label:Counter() for label in SERVICES};records={}
    for row in shard["records"]:
        ccn,state=row["ccn"],row["state"];key=state+":"+ccn
        require(re.fullmatch(r"[A-Z0-9]{6}",ccn) is not None and re.fullmatch(r"[A-Z]{2}",state) is not None and key not in records,"Unexpected public key")
        original=rows[(ccn,state)][0];v={}
        for label in SERVICES:
            classification=classify(original["Offers "+label+" Services"],{"yes":"yes","no":"no"})
            require(classification in {"yes","no","dash_marker"},"New source domain requires review")
            v[label]=classification;counts[label][classification]+=1
        records[key]=v
    for label,c in counts.items():
        e=expected[label]
        require(dict(c)=={k:v for k,v in {"yes":e["yes"],"no":e["no"],**e["other_states"]}.items() if v},"Qualified aggregate mismatch: "+label)
    return records,{k:dict(v) for k,v in counts.items()}
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--raw-dir",type=Path);parser.add_argument("--download",action="store_true");parser.add_argument("--out",type=Path,required=True);a=parser.parse_args()
    require(not a.out.exists(),"Output must be new")
    pin=next(s for s in load_lock(LOCK)["sources"] if s["key"]=="home-health")
    require(pin["sha256"]==SOURCE_SHA and pin["stored_rows"]==12409 and pin["release"]=="2026-10-21","Source lock drift")
    headers={s["source"]:[x["field"] for x in s["fields"]] for s in read(ROOT/"research/care_compare_pecos_exact_headers_20261126.json")["sources"]}
    evidence=read(ROOT/"research/qualified_data_use_20261126.json")["hha"]
    require(evidence["source_sha256"]==SOURCE_SHA and evidence["release"]==pin["release"],"Aggregate lineage drift")
    directory=(ROOT/"web/public-directory/home-health.json").read_bytes();shard=json.loads(directory)
    with tempfile.TemporaryDirectory(prefix="hha-service-") as tmp:
        source=materialize(pin,a.raw_dir,Path(tmp),a.download);rows=source_rows(source,pin,headers["home-health"])
        records,counts=qualify(shard,pin,rows,evidence["services"]);verify_raw(source,pin)
    require(len(records)==12409,"Full source identity reconciliation")
    data={"format_version":1,"scope":"existing public home-health provider source records only","source":"care-compare-home-health","release":pin["release"],"source_sha256":SOURCE_SHA,"public_directory_sha256":sha(directory),"fields":list(SERVICES),"records":records}
    encoded=(json.dumps(data,sort_keys=True,separators=(",",":"))+"\n").encode()
    audit={"source_release":pin["release"],"source_sha256":SOURCE_SHA,"public_directory_sha256":sha(directory),"provider_records":len(records),"exact_identity_fields":["ccn","name","address","city","state","zip"],"field_states":counts,"payload_sha256":sha(encoded),"payload_bytes":len(encoded),"dictionary":DICT_HHA,"reuse":REUSE_HHA,"scope":"Same pinned source and exact public identity fields, six service indicators only. Dash marker is not reported no. Historical offerings are not current availability, staffing, physical property or procurement evidence.","publication":"candidate_only"}
    a.out.mkdir(parents=True);(a.out/"hha-service-candidate.json").write_bytes(encoded);(a.out/"hha-service-audit.json").write_text(json.dumps(audit,indent=2)+"\n")
    print("HHA_SERVICE_PROJECTION_PASS",json.dumps(audit,sort_keys=True),flush=True)
if __name__=="__main__":main()
