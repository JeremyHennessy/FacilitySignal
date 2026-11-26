"""Archive already-qualified field observations and exact tracked data evidence.
No raw source files, private contacts, Pages edits, or pointer changes.
"""
import argparse,hashlib,json,os,re,sqlite3,subprocess,tempfile
from contextlib import closing
from pathlib import Path
import azure_national_archive as a
import institutional_observations as inst
from build_combined import require,sha,check_integrity,readonly
from restore_snapshot import LOCK,load_lock,materialize
from qualified_data_use import source_rows,compare_directory
from scripts import azure_source_archive as storage,azure_verified_extension as ext

ROOT=Path(__file__).resolve().parents[1]
QUAL=ROOT/"research/institutional_observations_qualification_20261126.json"
HEADERS=ROOT/"research/care_compare_pecos_exact_headers_20261126.json"
DATA_PATH=re.compile(r"(?:research|web|web/public-directory|web/hcris-capacity)/[A-Za-z0-9_.-]+\.json")
MAX_FILE=20_000_000
MAX_BYTES=100_000_000

def institutional_plan(national):
    prior=json.loads(QUAL.read_text())
    require(prior["qualification_run"]==45842903741 and prior["membership_and_state_filter_checks"]=="passed" and prior["sqlite_integrity"]=="ok","prior institutional qualification")
    require((prior["source_records"],prior["observations"],prior["field_rules"])==(27592,101534,10),"prior institutional scope")
    pins={p["key"]:p for p in load_lock(LOCK)["sources"]}
    headers={p["source"]:p for p in json.loads(HEADERS.read_text())["sources"]}
    inputs={}
    require(set(prior["sources"])==set(inst.RULES)=={"hospital","nursing","dialysis"},"institutional source scope")
    for key,s in prior["sources"].items():
        p=pins[key];h=headers[key];name="web/public-directory/"+key+".json"
        require(p["family"]=="care-compare" and p["sha256"]==h["source_sha256"]==s["source_sha256"] and p["release"]==s["release"] and p["stored_rows"]==s["providers"]==p["input_rows"],"source release drift")
        require(national["files"][name]["sha256"]==sha(ROOT/name)==s["public_sha256"],"approved directory drift")
        inputs[key]={"source_sha256":p["sha256"],"release":p["release"],"directory_sha256":s["public_sha256"]}
    meta={"kind":"derived_institutional_field_projection","base_database_sha256":national["receipt"]["database_sha256"],"qualification_sha256":sha(QUAL),"policy_version":1,"inputs":inputs}
    meta["sha256"]=hashlib.sha256(a.encode(meta)).hexdigest()
    return prior,pins,headers,meta

def expected_literals(key,prior):
    result={}
    for field,rule in inst.RULES[key].items():
        header,domain,_=rule;counts=prior["fields"][field]
        require(len(set(domain.values()))==len(domain) and set(counts)<=set(domain.values()),"field domain drift")
        result[header]={k:counts[v] for k,v in domain.items() if v in counts}
    return result

def build_institutional(store,national,root,prior,pins,headers):
    out=root/"projection.sqlite3";summary={}
    with closing(sqlite3.connect(out)) as db:
        inst.setup(db)
        for key in sorted(inst.RULES):
            p=pins[key];s=prior["sources"][key];name="web/public-directory/"+key+".json"
            a.verify(store,national["receipt"]["payload_prefix"]+"/"+name,national["files"][name])
            with tempfile.TemporaryDirectory(dir=root,prefix="source-") as d:
                raw=materialize(p,None,Path(d),True)
                rows=source_rows(raw,p,[x["field"] for x in headers[key]["fields"]])
                compare_directory(json.loads((ROOT/name).read_text()),p,rows)
                inst.add_source(db,key,p,rows,s["public_sha256"])
                counts=inst.validate(db,key,rows,expected_literals(key,s))
                require(counts==s["fields"] and len(rows)==s["providers"],"qualified memberships or counts differ")
                summary[key]={"providers":len(rows),"field_observations":len(rows)*len(inst.RULES[key]),"fields":counts}
        db.commit();check_integrity(db)
        counts=tuple(db.execute("SELECT count(*) FROM "+t).fetchone()[0] for t in ("candidate_provider","candidate_field","candidate_observation"))
        require(counts==(27592,10,101534),"institutional projection counts")
    return out,{"stored_field_observations":counts[2],"source_provider_records":counts[0],"field_rules":counts[1],"sources":summary,"new_publisher_release":False,"membership_and_state_filter_checks":"passed","scope":"Previously qualified institutional field values only; source-scoped, no new facility identities or clinical inference."}

def data_plan(national):
    # Archive the exact tracked JSON data, not arbitrary workspace files.
    names=sorted(p for p in subprocess.check_output(["git","ls-files","-z","--","research","web"],cwd=ROOT).decode().split("\0") if DATA_PATH.fullmatch(p))
    require(0<len(names)==len(set(names))<=300,"tracked data count")
    all_files=[];changes=[];unchanged=[]
    for name in names:
        path=ROOT/name
        r=a.rec(name,path)
        require(0<r["bytes"]<=MAX_FILE,"data file bound")
        json.loads(path.read_bytes())
        all_files.append(r)
        (unchanged if national["files"].get(name)==r else changes).append(r)
    require(sum(x["bytes"] for x in all_files)<=MAX_BYTES,"tracked data total bound")
    require({"web/hcris-capacity/hospital.json","web/hcris-capacity/snf.json"}<=set(names),"current approved capacity packs missing")
    cap=json.loads((ROOT/"research/hcris_capacity_candidate_receipts_20261126.json").read_text())
    for form,r in cap["forms"].items():
        path=ROOT/"web/hcris-capacity"/(form+".json")
        require(path.stat().st_size==r["ephemeral_candidate_bytes"] and sha(path)==r["ephemeral_candidate_sha256"],"public capacity pack drift")
    inputs={"base_receipt_sha256":national["receipt_sha256"],"policy_version":1,"tracked_data_files":all_files}
    meta={"kind":"repository_data_evidence_snapshot","sha256":hashlib.sha256(a.encode(inputs)).hexdigest(),"inputs":inputs}
    return meta,all_files,changes,unchanged

def build_data(store,national,root,files,changes,unchanged):
    out=root/"projection.sqlite3"
    for r in unchanged:
        a.verify(store,national["receipt"]["payload_prefix"]+"/"+r["path"],r)
    with closing(sqlite3.connect(out)) as db:
        db.execute("CREATE TABLE file_manifest(path TEXT PRIMARY KEY, bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, disposition TEXT NOT NULL CHECK(disposition IN ('base','supplement'))) WITHOUT ROWID")
        db.execute("CREATE TABLE exact_data_files(path TEXT PRIMARY KEY REFERENCES file_manifest(path), content BLOB NOT NULL) WITHOUT ROWID")
        db.execute("PRAGMA foreign_keys=ON")
        for r in unchanged:
            db.execute("INSERT INTO file_manifest VALUES(?,?,?,?)",(r["path"],r["bytes"],r["sha256"],"base"))
        for r in changes:
            data=(ROOT/r["path"]).read_bytes()
            require(len(data)==r["bytes"] and hashlib.sha256(data).hexdigest()==r["sha256"],"tracked data changed")
            db.execute("INSERT INTO file_manifest VALUES(?,?,?,?)",(r["path"],r["bytes"],r["sha256"],"supplement"))
            db.execute("INSERT INTO exact_data_files VALUES(?,?)",(r["path"],data))
        db.commit();check_integrity(db)
        require(db.execute("SELECT count(*) FROM file_manifest").fetchone()[0]==len(files),"file manifest count")
        require(db.execute("SELECT count(*) FROM exact_data_files").fetchone()[0]==len(changes),"supplement count")
        observed=[]
        for path,data in db.execute("SELECT path,content FROM exact_data_files ORDER BY path"):
            observed.append(a.bytes_record(path,data))
        require(observed==changes,"exact supplemental data reconstruction")
    return out,{"tracked_data_file_count":len(files),"base_file_count":len(unchanged),"supplemental_file_count":len(changes),"tracked_data_bytes":sum(r["bytes"] for r in files),"supplemental_data_bytes":sum(r["bytes"] for r in changes),"supplemental_paths":[r["path"] for r in changes],"complete_manifest":files,"new_publisher_release":False,"scope":"Exact committed research and public data JSON; base copies verified, newer files retained byte-for-byte. No new source observations."}

def run(store,scope):
    national=storage.national_manifest(store)
    if scope=="institutional":
        prior,pins,headers,meta=institutional_plan(national);key="institutional-field-observations"
    else:
        meta,files,changes,unchanged=data_plan(national);key="repository-data-evidence"
    rec=storage.existing(store,key,meta["sha256"])
    if rec is not None:
        require(rec["publisher"]==meta and rec["base_receipt_sha256"]==national["receipt_sha256"] and rec["public_promotion"] is False,"existing supplemental receipt drift")
        if scope=="institutional":
            require(rec["summary"]["stored_field_observations"]==prior["observations"],"existing institutional count")
        else:
            require(rec["summary"]["complete_manifest"]==files and rec["summary"]["supplemental_file_count"]==len(changes),"existing evidence manifest")
        ext.unchanged(store,national)
        return rec
    with tempfile.TemporaryDirectory(prefix="qualified-private-data-") as d:
        root=Path(d)
        out,summary=build_institutional(store,national,root,prior,pins,headers) if scope=="institutional" else build_data(store,national,root,files,changes,unchanged)
        audit={"publisher":meta,"summary":summary,"projection_sha256":sha(out),"projection_bytes":out.stat().st_size,"public_promotion":False,"reuse_review":"pending"}
        rec=storage.publish(store,key,meta,out,audit,root,national)
    ext.unchanged(store,national)
    return rec

def main():
    p=argparse.ArgumentParser();p.add_argument("--scope",choices=("institutional","evidence"),required=True);p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ);store=storage.SourceAzure(os.environ)
    try:rec=run(store,args.scope)
    finally:store.close()
    with args.receipt.open("xb") as f:f.write(a.encode(rec))
    print("PRIVATE_QUALIFIED_DATA_COMPLETE",args.scope,json.dumps(rec,sort_keys=True),flush=True)
if __name__=="__main__":main()
