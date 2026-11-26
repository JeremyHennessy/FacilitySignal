"""Exact, limited CMS nursing-chain public candidate; no raw rows retained.

Chain grouping is a publisher-defined affiliation, NOT an owner, legal entity,
physical site, risk determination or current portfolio. No personal-owner,
contact, rating, penalty or address fields are copied into the candidate.
"""
import argparse
import json
import re
import tempfile
from collections import Counter,defaultdict
from pathlib import Path
from qualified_data_use import ROOT, read, sha, source_rows, compare_directory, need
from restore_snapshot import materialize

NAME="nursing-chain-evidence.json"
RELEASE="2026-10-28"
SOURCE="ab70309ae6f0ee86b19fe9acb61a6d2953f970d3b09e80bb9b090e4b19ce35a2"
DIRECTORY="36363899e56c97433686ce8617a7d4b557b272a155e8a8eba1822c6f7a36e3ce"
SCOPE="CMS nursing-home chain affiliation; publisher-defined historical group, not legal ownership."
COUNTS={"groups":612,"assigned":10227,"unassigned":4459,"providers":14686}
BANDS={"2-4":66,"5-19":419,"20-99":118,"100+":9}

def token(v):
    return isinstance(v,str) and re.fullmatch(r"[0-9]{1,8}",v) is not None

def name(v):
    return isinstance(v,str) and bool(v) and len(v)<=300 and v==" ".join(v.upper().split()) and all(c.isprintable() for c in v)

def metadata(root=ROOT):
    pin=next(x for x in read(root/"research/snapshot_release_20261125.json")["sources"] if x["key"]=="nursing")
    need((pin["release"],pin["sha256"],pin["stored_rows"],pin["bytes"])==(RELEASE,SOURCE,COUNTS["providers"],9218563),"pinned publisher release changed")
    audit=read(root/"research/nursing_semantic_audit_20261126.json")
    a=next(x for x in audit["audits"] if x["group"]=="chains")
    need(audit["qualification_run"]==45826186143 and a["source_pins"]["nursing"]=={"release":RELEASE,"sha256":SOURCE,"rows":COUNTS["providers"]},"prior chain qualification lineage")
    r=a["result"]; c=r["chains"]; n=r["nursing"]
    need(c["groups"]==c["single_reported_name"]==c["consistent_reported_size"]==c["reported_size_matches_observed_members"]==COUNTS["groups"] and c["names_associated_with_multiple_chain_ids"]==0 and c["observed_membership_size_bands"]==BANDS,"prior group reconciliation")
    need(n["rows"]==COUNTS["providers"] and n["valid_chain_id"]==COUNTS["assigned"] and n["blank_chain_id"]==COUNTS["unassigned"] and not any(n[k] for k in ("unrecognized_chain_id","chain_id_name_conflict","chain_id_size_conflict")),"prior provider reconciliation")
    path=root/"web/public-directory/nursing.json"
    need(sha(path)==DIRECTORY,"directory bytes changed")
    directory=read(path)
    need(directory["source"]=="nursing" and directory["release"]==RELEASE and directory["row_count"]==len(directory["records"])==COUNTS["providers"],"directory metadata")
    return pin,directory

def build(raw,root=ROOT):
    pin,directory=metadata(root)
    headers=next(x for x in read(root/"research/care_compare_pecos_exact_headers_20261126.json")["sources"] if x["source"]=="nursing")
    need(headers["source_sha256"]==SOURCE,"source header pin")
    rows=source_rows(raw,pin,[x["field"] for x in headers["fields"]])
    compare_directory(directory,pin,rows)
    groups={};members=[]
    for (ccn,state),(r,_) in sorted(rows.items(),key=lambda x:(x[0][1],x[0][0])):
        cid=r["Chain ID"].strip()
        label=" ".join(r["Chain Name"].upper().split())
        size=r["Number of Facilities in Chain"].strip()
        if not cid:
            need(not label and not size,"missing ID with group fields")
            members.append([ccn,state,None]);continue
        need(token(cid) and name(label) and re.fullmatch(r"[0-9]{1,5}",size) is not None and int(size)>=2,"invalid chain source fields")
        entry=[cid,label,int(size)]
        need(cid not in groups or groups[cid]==entry,"conflicting group labels or sizes")
        groups[cid]=entry;members.append([ccn,state,cid])
    pack={"format_version":1,"scope":SCOPE,"source":"nursing","release":RELEASE,"source_sha256":SOURCE,"directory_sha256":DIRECTORY,"groups":sorted(groups.values()),"members":members}
    validate(pack,directory)
    return pack

def validate(pack,directory):
    need(set(pack)=={"format_version","scope","source","release","source_sha256","directory_sha256","groups","members"} and pack["format_version"]==1 and pack["scope"]==SCOPE and pack["source"]=="nursing" and pack["release"]==RELEASE and pack["source_sha256"]==SOURCE and pack["directory_sha256"]==DIRECTORY,"candidate metadata")
    need(isinstance(pack["groups"],list) and len(pack["groups"])==COUNTS["groups"] and isinstance(pack["members"],list) and len(pack["members"])==COUNTS["providers"],"candidate record count")
    groups={}
    labels=set()
    for g in pack["groups"]:
        need(isinstance(g,list) and len(g)==3 and token(g[0]) and name(g[1]) and type(g[2]) is int and 2<=g[2]<=COUNTS["assigned"],"candidate group schema")
        cid,label,n=g;need(cid not in groups and label not in labels,"duplicate group identifier or normalized name")
        groups[cid]=n;labels.add(label)
    keys={(r["ccn"],r["state"]) for r in directory["records"]}
    need(len(keys)==COUNTS["providers"],"duplicate directory keys")
    seen=set();counts=Counter()
    for row in pack["members"]:
        need(isinstance(row,list) and len(row)==3,"candidate member schema")
        ccn,state,cid=row; k=(ccn,state)
        need(k in keys and k not in seen and (cid is None or isinstance(cid,str) and cid in groups),"member scope or duplicate")
        seen.add(k);counts[cid]+=1
    need(seen==keys and counts[None]==COUNTS["unassigned"] and sum(n for k,n in counts.items() if k is not None)==COUNTS["assigned"],"complete membership reconciliation")
    need({k:v for k,v in counts.items() if k is not None}==groups,"reported size and observed group membership differ")
    bands=Counter("2-4" if n<=4 else "5-19" if n<=19 else "20-99" if n<=99 else "100+" for n in groups.values())
    need(dict(bands)==BANDS,"prior group size distribution mismatch")
    return dict(COUNTS)

def check(path,root=ROOT):
    _,directory=metadata(root)
    need(path.is_file() and not path.is_symlink() and path.stat().st_size<2000000,"missing or oversized public chain pack")
    summary=validate(read(path),directory)
    return {**summary,"bytes":path.stat().st_size,"sha256":sha(path),"release":RELEASE,"source_sha256":SOURCE,"directory_sha256":DIRECTORY,"publisher":"CMS","public_promotion":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=("build","check"))
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path)
    a=p.parse_args()
    if a.mode=="build":
        need(not a.output.exists(),"new candidate output required")
        pin,_=metadata()
        with tempfile.TemporaryDirectory() as d:
            raw=materialize(pin,a.raw_dir,Path(d),a.download)
            payload=build(raw)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(payload,f,ensure_ascii=False,sort_keys=True,separators=(",",":"));f.write("\n")
    print("NURSING_CHAIN_PUBLIC_CANDIDATE",json.dumps(check(a.output),sort_keys=True),flush=True)
if __name__=="__main__":main()
