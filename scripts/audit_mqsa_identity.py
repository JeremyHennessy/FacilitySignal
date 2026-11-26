"""Independent exact institutional evidence audit for the already-qualified FDA MQSA release.

Only aggregate match dispositions are retained. No row-level output, no stable
FDA facility ID, no facility merge, installed unit or current certificate inference.
"""
import argparse,hashlib,json,re,sqlite3,tempfile,sys
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.qualify_fda_mqsa import download,audit_archive,require,JURISDICTIONS,MILITARY_MAIL
from scripts.audit_epa_medical_identity import pinned_json,PINS
ROOT=Path(__file__).resolve().parents[1]
PIN="fb0c74333ade998ce28c6b5f342324f5ff4c46d716c45332634513edddf1b33a"
def norm(x):return " ".join(str(x or "").casefold().split())
def zip5(x):
    x=str(x or "").strip()
    return x[:5] if re.fullmatch(r"[0-9]{5}(?:-?[0-9]{4})?",x) else ""
def text_key(r):
    state=str(r.get("state","")).strip()
    values=(state,norm(r.get("address")),norm(r.get("city")),zip5(r.get("zip")))
    return values if state in JURISDICTIONS and all(values) else None
def index_rows(rows):
    names=defaultdict(set);addresses=defaultdict(set);allrows={}
    for dataset,r in rows:
        key=(dataset,r["ccn"])
        require(key not in allrows,"Duplicate provider source key")
        allrows[key]=r
        state=r["state"];name=norm(r["name"])
        if state in JURISDICTIONS and name:names[(state,name)].add(key)
        addr=text_key(r)
        if addr:addresses[addr].add(key)
    return names,addresses,allrows
def public_directory():
    folder=ROOT/"web/public-directory";manifest=pinned_json(folder/"manifest.json","manifest")
    rows=[]
    for key in sorted(set(PINS)-{"manifest"}):
        d=pinned_json(folder/(key+".json"),key)
        require(d["source"]==key and d["row_count"]==len(d["records"])==manifest["sources"][key]["source_rows"],"Provider shard mismatch")
        rows.extend((key,r) for r in d["records"])
    require(len(rows)==48004==manifest["provider_rows"],"Provider row reconciliation")
    return index_rows(rows)
def match(row,index):
    names,addresses,allrows=index
    if row["state"] not in JURISDICTIONS:return "out_of_jurisdiction",set(),set(),set()
    name=norm(row["name"]);state=row["state"]
    name_hits=names.get((state,name),set()) if name else set()
    key=text_key(row);addr_hits=addresses.get(key,set()) if key else set()
    both=name_hits & addr_hits
    if both:bucket="name_and_address_text_single" if len(both)==1 else "name_and_address_text_multiple"
    elif name_hits and addr_hits:bucket="name_and_address_candidates_disagree"
    elif name_hits:bucket="name_state_only"
    elif addr_hits:bucket="address_city_zip_state_only"
    elif not key or not name:bucket="incomplete_match_fields"
    else:bucket="no_exact_candidate"
    return bucket,name_hits,addr_hits,both
def audit_rows(db,index):
    buckets=Counter();pair_counts=Counter();category_counts=Counter();seen=set();n=0
    for name,address,city,state,zip in db.execute("SELECT name,address1,city,state,zip FROM mqsa_projection ORDER BY ordinal"):
        bucket,byname,byaddress,both=match({"name":name,"address":address,"city":city,"state":state,"zip":zip},index);n+=1;buckets[bucket]+=1
        pair_counts["name_state_candidate_pairs"]+=len(byname);pair_counts["address_text_candidate_pairs"]+=len(byaddress);pair_counts["corroborated_candidate_pairs"]+=len(both)
        seen.update(both)
        for dataset,_ in both:category_counts[dataset]+=1
    require(sum(buckets.values())==n and pair_counts["corroborated_candidate_pairs"]==sum(category_counts.values()),"Candidate reconciliation")
    return {"source_rows":n,"match_dispositions":dict(buckets),"pair_counts":dict(pair_counts),"corroborated_candidate_pairs_by_provider_source":dict(category_counts),"distinct_corrob_provider_source_rows":len(seen),"canonical_matches":0,"confirmed_equipment_installations":0,"retained_row_level_records":0,
        "limits":"Exact casefold/whitespace name and reported state, plus literal FDA first address line, city and ZIP5 agreement to CMS reported address. Address-only, name-only and discordant candidates stay separate. Text agreement is not physical-site or equipment proof; mobile classification incomplete. Military-mail and unsupported jurisdictions excluded from candidates. No row-level output."}
def main():
    p=argparse.ArgumentParser();p.add_argument("--audit",type=Path,required=True);p.add_argument("--archive",type=Path);p.add_argument("--download",action="store_true");a=p.parse_args()
    require(bool(a.archive)!=a.download and not a.audit.exists(),"Choose one authorized source and new audit")
    with tempfile.TemporaryDirectory(prefix="mqsa-identity-") as temp:
        path=a.archive or Path(temp)/"source.zip"
        if a.download:meta=download(path)
        else:meta={}
        require(path.is_file() and not path.is_symlink(),"No authorized archive")
        with path.open("rb") as f:require(hashlib.file_digest(f,"sha256").hexdigest()==PIN,"Source changed; no retry")
        with closing(sqlite3.connect(":memory:")) as db:
            source=audit_archive(db,path,allow_pinned_width_exception=True)
            require(source["input_rows"]==source["stored_rows"]==9146 and source["schema_exception_rows"]==6 and source["unresolved_rows"]==0,"Prior source qualification mismatch")
            result=audit_rows(db,public_directory())
        with path.open("rb") as f:require(hashlib.file_digest(f,"sha256").hexdigest()==PIN,"Source mutated")
    require(result["source_rows"]==9146,"Source row mismatch")
    result.update({"source_sha256":PIN,"provider_rows":48004,"cms_directory_git_blobs":PINS,"source_metadata":meta,"reuse_review":"pending","qualification":"aggregate_institutional_identity_candidates_only"})
    a.audit.parent.mkdir(parents=True,exist_ok=True);a.audit.write_text(json.dumps(result,indent=2)+"\n")
    print("MQSA_IDENTITY_AUDIT",json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":main()
