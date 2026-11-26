"""Offline verification of expanded source release bytes on authorized private storage.

No network, writes, copying, row parsing, or publication. This verifies archive
files against evidence pins, not the semantics or integration of their contents.
"""
import argparse,hashlib,json,re
from pathlib import Path
from urllib.parse import urlsplit
from build_combined import require
from private_snapshot_archive import private_directory
ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/"research/expanded_source_lock_20261126.json"
HOSTS={"data.cms.gov","data.hrsa.gov","qcor.cms.gov","www.accessdata.fda.gov"}
def validate_item(x):
    require(re.fullmatch(r"fs-[0-9]{3}-[a-z0-9-]+\.(csv|xlsx|zip)",x["file"]) is not None,"unsafe archive filename")
    require(type(x["bytes"]) is int and x["bytes"]>0 and re.fullmatch(r"[a-f0-9]{64}",x["sha256"]),"invalid source pin")
    u=urlsplit(x["url"])
    require(u.scheme=="https" and u.hostname in HOSTS and u.port in (None,443) and not u.username and not u.password and not u.fragment,"source URL scope")
def load_lock(path=LOCK):
    l=json.loads(path.read_text(encoding="utf-8"));rows=l["expanded_sources"]
    require(l["format_version"]==1 and l["source_count"]==len(rows)==17,"source lock coverage")
    require(len({x["source_id"] for x in rows})==len(rows),"duplicate source id")
    files=[]
    for row in rows:
        require(re.fullmatch(r"FS-[0-9]{3}",row["source_id"]) is not None,"source ID format")
        require(row["scope"] in {"ephemeral_projection","aggregate_screening"} and row["retained_row_level_records"]==0,"scope boundary")
        require(0<row["qualified_rows"]<=row["input_rows"],"row count")
        for item in [row,*row.get("required_metadata",[])]:
            validate_item(item);files.append(item)
    require(len({x["file"] for x in files})==len(files)==18,"file coverage")
    require(sum(x["bytes"] for x in files)==l["raw_source_bytes"],"byte reconciliation")
    for scope,key in (("ephemeral_projection","ephemeral_projection_records"),("aggregate_screening","aggregate_screened_records")):
        require(sum(x["qualified_rows"] for x in rows if x["scope"]==scope)==l[key],"count reconciliation")
    return l
def verify_files(lock,root,selected=None):
    root=private_directory(root)
    wanted=set(selected or (r["source_id"] for r in lock["expanded_sources"]))
    require(bool(wanted) and wanted<={r["source_id"] for r in lock["expanded_sources"]},"unknown source id")
    findings=[]
    for row in lock["expanded_sources"]:
        if row["source_id"] not in wanted:continue
        for x in [row,*row.get("required_metadata",[])]:
            path=root/x["file"];status="missing"
            if path.is_symlink():status="symlink_rejected"
            elif path.exists():
                if not path.is_file():status="not_regular"
                elif path.stat().st_size!=x["bytes"]:status="size_mismatch"
                else:
                    with path.open("rb") as f:digest=hashlib.file_digest(f,"sha256").hexdigest()
                    status="verified" if digest==x["sha256"] else "checksum_mismatch"
            findings.append({"source_id":row["source_id"],"file":x["file"],"status":status})
    return {"selected_sources":len(wanted),"expected_files":len(findings),"verified_files":sum(x["status"]=="verified" for x in findings),
            "all_expanded_sources_selected":len(wanted)==len(lock["expanded_sources"]),"file_results":findings,
            "limits":"Byte verification only. Not a restore, reusable storage authorization, domain check, or persistent integration. The original 19-source snapshot is a separate lock."}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir",type=Path);p.add_argument("--source",nargs="+");p.add_argument("--authorized-private-storage",action="store_true");p.add_argument("--manifest-only",action="store_true")
    a=p.parse_args();l=load_lock()
    if a.manifest_only:
        require(a.raw_dir is None and a.source is None,"manifest-only does not inspect files")
        print(json.dumps({k:l[k] for k in ("source_count","raw_source_bytes","ephemeral_projection_records","aggregate_screened_records")},sort_keys=True))
        return
    require(a.raw_dir is not None and a.authorized_private_storage,"explicit authorized private storage required")
    result=verify_files(l,a.raw_dir,a.source)
    print(json.dumps(result,sort_keys=True))
    require(result["verified_files"]==result["expected_files"],"archive byte verification incomplete")
if __name__=="__main__":main()
