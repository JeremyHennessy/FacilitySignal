"""Build narrowly scoped public institutional directory and citation aggregates.

No raw files, individual owner rows, QCOR rows, certification registry rows,
contact information, or unrestricted source projections are copied.
"""
import argparse, hashlib, json, sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def digest(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def require(test,msg):
    if not test:raise ValueError(msg)
def write(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
def main(db_path,manifest_path,out):
    lock=json.loads((ROOT/"research/snapshot_release_20261125.json").read_text())
    manifest=json.loads(manifest_path.read_text())
    require(digest(db_path)==manifest["db_sha256"],"retained database manifest digest mismatch")
    sources={s["key"]:s for s in lock["sources"] if s["family"]=="care-compare"}
    with sqlite3.connect(db_path.resolve().as_uri()+"?mode=ro",uri=True) as db:
        db.row_factory=sqlite3.Row
        require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","source DB integrity")
        require(not db.execute("PRAGMA foreign_key_check").fetchone(),"source DB foreign keys")
        actual={r["dataset"]:r for r in db.execute("SELECT r.* FROM current_release c JOIN releases r ON r.id=c.release_id")}
        require(set(actual)==set(sources),"source release set mismatch")
        require(not out.exists(),"new output directory required")
        out.mkdir(parents=True)
        provider_total=citation_total=0
        jurisdictions=set()
        counts={}
        for name,s in sorted(sources.items()):
            a=actual[name]
            require(a["sha256"]==s["sha256"] and a["published_on"]==s["release"] and a["stored_rows"]==s["stored_rows"],"source lock mismatch: "+name)
            if name.startswith("nursing-"):
                records=[dict(r) for r in db.execute("""SELECT d.ccn,d.state,
                    coalesce(f.name,min(d.provider_name)) AS name,count(*) AS citation_rows
                    FROM findings d LEFT JOIN facilities f
                    ON f.dataset='nursing' AND f.ccn=d.ccn AND f.state=d.state
                    WHERE d.dataset=? GROUP BY d.ccn,d.state,f.name ORDER BY d.state,name COLLATE NOCASE,d.ccn""",(name,))]
                n=sum(r["citation_rows"] for r in records)
                citation_total+=n
            else:
                records=[dict(r) for r in db.execute("""SELECT ccn,name,address,city,state,zip,capacity
                    FROM facilities WHERE dataset=? ORDER BY state,name COLLATE NOCASE,ccn""",(name,))]
                n=len(records)
                provider_total+=n
                jurisdictions.update(r["state"] for r in records)
            require(n==s["stored_rows"],"projection count mismatch: "+name)
            write(out/(name+".json"),{"source":name,"release":s["release"],"row_count":n,"records":records})
            counts[name]={"source_rows":n,"published_records":len(records)}
        require(provider_total==sum(s["stored_rows"] for s in sources.values() if not s["key"].startswith("nursing-")),"provider reconciliation")
        require(citation_total==sum(s["stored_rows"] for s in sources.values() if s["key"].startswith("nursing-")),"citation reconciliation")
        write(out/"manifest.json",{"as_of":lock["as_of"],"source_artifact_id":15046953633,"source_database_sha256":manifest["db_sha256"],"provider_rows":provider_total,"citation_source_rows":citation_total,"jurisdictions":sorted(jurisdictions),"sources":counts,"limitations":["Narrow public Care Compare provider projection and CCN/state citation aggregates only.","Counts are historical source rows, not active deficiency counts.","No registry, QCOR, PECOS, raw data or private customer records."]})
        print("PUBLIC_DIRECTORY_VERIFIED",json.dumps({"providers":provider_total,"citation_source_rows":citation_total,"jurisdictions":len(jurisdictions),"files":len(counts)},sort_keys=True))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();main(a.db,a.manifest,a.output)
