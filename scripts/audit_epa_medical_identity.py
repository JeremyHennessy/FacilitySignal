"""Pinned, aggregate-only candidate matching. No EPA rows or candidate pairs published."""
import argparse
import csv
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.qualify_epa_sdwa import download,require,key_format,MEMBER,MAX_EXPANDED
from scripts.audit_epa_medical_area import PIN,area,VALID_FORMATS

ROOT=Path(__file__).resolve().parents[1]
PINS={
 "dialysis":"27c5c03e90451e90b703e61beb9c316951a60c02",
 "home-health":"fb20daad02d01fb23fbfcd60f9ad3b77447e9bbf",
 "hospice":"33bae4cee004d1e6f97ce587e7e0d5a20b2af14b",
 "hospital":"b0f0c73946064b5cb754912f685d2fcf975fb02b",
 "long-term-hospital":"a844990b8de32df47b73fe218dac66fb3beba850",
 "manifest":"8123501588260afc66337412c2212076371d8616",
 "nursing":"35274944fb33e1a617b6e029e8c1a837f3ad97ad",
 "rehabilitation":"009eca9c0400521f8547bc542fa51cadb85be317",
}
FIELDS={"PWSID","PWS_NAME","STATE_CODE","SERVICE_AREA_TYPE_CODE","SERVICE_AREA_TYPE_DESC","PWS_ACTIVITY_CODE"}

def norm(value):
    return " ".join(value.casefold().split())

def pinned_json(path,key):
    b=path.read_bytes()
    require(hashlib.sha1(("blob "+str(len(b))+"\0").encode()+b).hexdigest()==PINS[key],"directory blob drift: "+key)
    return json.loads(b)

def directory(root):
    manifest=pinned_json(root/"manifest.json","manifest")
    index=defaultdict(set);n=0;seen=set();states=set(manifest["jurisdictions"])
    for dataset in sorted(set(PINS)-{"manifest"}):
        data=pinned_json(root/(dataset+".json"),dataset)
        require(data["source"]==dataset and len(data["records"])==data["row_count"]==manifest["sources"][dataset]["source_rows"],"directory shard reconciliation")
        for row in data["records"]:
            key=(dataset,row["ccn"])
            require(key not in seen and row["state"] in states and norm(row["name"]),"directory row integrity")
            seen.add(key);n+=1
            index[(row["state"],norm(row["name"]))].add(key)
    require(n==manifest["provider_rows"]==48004 and len(states)==56,"directory total")
    return index,states,n

def match_bucket(row,index,states):
    if key_format(row["PWSID"]) not in VALID_FORMATS:return "unresolved_identifier",set()
    state=row["STATE_CODE"].strip()
    name=norm(row["PWS_NAME"])
    if state not in states or not name:return "missing_or_unsupported_name_state",set()
    hits=index.get((state,name),set())
    return ("no_exact_candidate" if not hits else "one_candidate" if len(hits)==1 else "multiple_candidates"),hits

def audit(path,index,states):
    buckets=Counter();activity=Counter();category=Counter();matched_rows=set();n=medical=pairs=0
    with closing(sqlite3.connect(":memory:")) as db,zipfile.ZipFile(path) as z:
        m=z.infolist()
        require(len(m)==1 and m[0].filename==MEMBER and 0<m[0].file_size<=MAX_EXPANDED and not m[0].flag_bits&1,"archive bounds")
        db.execute("CREATE TABLE keys(id TEXT PRIMARY KEY)")
        with z.open(m[0]) as raw,io.TextIOWrapper(raw,encoding="utf-8-sig",newline="") as stream:
            reader=csv.DictReader(stream,strict=True);h=reader.fieldnames or []
            require(len(h)==len(set(h)) and FIELDS<=set(h),"schema")
            for row in reader:
                require(None not in row and all(v is not None for v in row.values()),"malformed row")
                key=row["PWSID"];n+=1
                require(key and key==key.strip() and db.execute("INSERT OR IGNORE INTO keys VALUES(?)",(key,)).rowcount==1,"key integrity")
                if area(row["SERVICE_AREA_TYPE_CODE"],row["SERVICE_AREA_TYPE_DESC"])!="exact_code_and_description":continue
                medical+=1;bucket,hits=match_bucket(row,index,states);buckets[bucket]+=1
                code=row["PWS_ACTIVITY_CODE"].strip()
                activity[(bucket,code if code in {"A","I","N","M","P"} else "other_or_missing")]+=1
                pairs+=len(hits);matched_rows.update(hits)
                for dataset,_ in hits:category[dataset]+=1
        require(n==db.execute("SELECT count(*) FROM keys").fetchone()[0],"source reconciliation")
    require(medical==sum(buckets.values())==sum(activity.values()) and pairs==sum(category.values()),"candidate reconciliation")
    return {"source_rows":n,"medical_area_rows":medical,"candidate_state_counts":dict(buckets),
            "candidate_pairs":pairs,"distinct_cms_source_rows_in_candidates":len(matched_rows),
            "candidate_pairs_by_cms_dataset":dict(category),
            "raw_water_activity_by_candidate_state":{b:{c:v for (k,c),v in activity.items() if k==b} for b in buckets},
            "limits":"Exact casefold/whitespace-normalized name and state only. No address or physical-site agreement, current operation, ownership, equipment, compliance or opportunity inference. Unresolved-format IDs never match. Candidate pairs are not verified relationships; no row-level output."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit",type=Path,required=True);p.add_argument("--source",type=Path);p.add_argument("--download",action="store_true");a=p.parse_args()
    require(not a.audit.exists() and bool(a.source)!=a.download,"select exactly one input and new audit")
    index,states,provider_rows=directory(ROOT/"web/public-directory")
    with tempfile.TemporaryDirectory(prefix="epa-medical-identity-") as t:
        path=a.source or Path(t)/"source.zip";meta=download(path) if a.download else {}
        require(path.is_file() and not path.is_symlink(),"source missing")
        with path.open("rb") as f:require(hashlib.file_digest(f,"sha256").hexdigest()==PIN,"source drift")
        result=audit(path,index,states)
        require(result["source_rows"]==434757 and result["medical_area_rows"]==1712 and result["candidate_state_counts"].get("unresolved_identifier")==11,"previous source baseline mismatch")
        with path.open("rb") as f:require(hashlib.file_digest(f,"sha256").hexdigest()==PIN,"source mutated")
    result.update({"epa_source_sha256":PIN,"cms_directory_git_blobs":PINS,"cms_provider_rows":provider_rows,"retrieval":meta,"reuse_review":"pending"})
    a.audit.parent.mkdir(parents=True,exist_ok=True);a.audit.write_text(json.dumps(result,indent=2)+"\n")
    print("EPA_MEDICAL_IDENTITY_AGGREGATE",json.dumps(result),flush=True)

if __name__=="__main__":main()
