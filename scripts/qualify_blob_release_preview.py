"""Read-only assembly of a coherent private directory/market release preview.

Only aggregate qualification receipts may leave the temporary workspace.
The historical national lock, existing public assets and Azure pointers are immutable.
"""
import argparse,copy,json,os,re,sqlite3,tempfile
from contextlib import closing
from datetime import date
from pathlib import Path
import azure_national_archive as archive
import facilitysignal as fs
from build_combined import require,sha,readonly,check_integrity
from scripts import azure_verified_extension as ext,weekly_azure_refresh as weekly
from scripts import build_market_summary as market,requalify_care_compare_dependencies as deps,requalify_dialysis_blob_dependency as dialysis,requalify_hospital_nursing_dependencies as institutional
from scripts.azure_inventory import verify_inventory
ROOT=Path(__file__).resolve().parents[1]
LOCK="research/snapshot_release_20261125.json"
SOURCES=set(fs.CATALOG)
NEW_STATES={"private_candidate_qualified","candidate_already_qualified"}
DEPS={"home-health":["home_health_service_evidence"],"dialysis":["dialysis_registry_corroboration","institutional_public_flags_pack_requalification"],"long-term-hospital":["long_term_hospital_capacity_enrichment"],"hospital":["hospital_infrastructure_and_laboratory_evidence","institutional_public_flags_pack_requalification"],"nursing":["nursing_provider_and_chain_evidence","nursing_citation_name_join","institutional_public_flags_pack_requalification"],"nursing-health":["nursing_health_citation_evidence"],"nursing-fire":["nursing_fire_citation_evidence"],"hospice":[],"rehabilitation":[]}
class ReadOnlyWeeklyAzure(weekly.WeeklyAzure):
    def create(self,*args,**kwargs):raise ValueError("release preview is read-only")
    def delete_probe(self,*args,**kwargs):raise ValueError("release preview is read-only")

def source_pins(lock):
    p=[x for x in lock["sources"] if x["family"]=="care-compare"]
    pins={x["key"]:x for x in p}
    require(len(p)==len(pins)==9 and set(pins)==SOURCES,"all nine unique source pins required")
    return pins

def selection(report,pins):
    require(report["format_version"]==1 and report["policy_version"]==weekly.POLICY_VERSION and report["public_promotion"] is False,"weekly report scope")
    require(not report["failed_checks"],"weekly checks incomplete")
    entries=report["sources"];require(SOURCES<=set(entries),"weekly Care Compare coverage")
    selected={};blocked={}
    for k,old in sorted(pins.items()):
        item=entries[k];state=item["state"]
        if state not in NEW_STATES|{"unchanged"}:blocked[k]=state;continue
        meta=item["publisher"];count=item["api_count"];observed=weekly.release_state(meta,count,old)
        require(item["published_baseline_release"]==old["release"],"baseline release mismatch")
        if state=="unchanged":require(observed=="unchanged","unverified unchanged report");continue
        require(observed=="new_release","invalid changed-source policy")
        result=item["candidate"];imp=result["import"]
        require(result["publisher"]==meta and result["api_count"]==count,"candidate metadata")
        require(imp["status"]=="imported" and imp["dataset"]==k and imp["input_rows"]==count and imp["stored_rows"]>0 and imp["stored_rows"]+imp["duplicate_rows"]==count,"candidate import reconciliation")
        require(imp["sha256"]==result["source_sha256"] and re.fullmatch(r"[0-9a-f]{64}",result["source_sha256"]) is not None,"candidate source digest")
        require(type(result["source_bytes"]) is int and 0<result["source_bytes"]<=350_000_000,"candidate source byte bounds")
        selected[k]={"identity":weekly.cms_key(k,meta,count),"result":result,"source":{"family":"care-compare","key":k,"release":meta["released"],"sha256":result["source_sha256"],"bytes":result["source_bytes"],"input_rows":count,"stored_rows":imp["stored_rows"],"excluded_rows":imp["duplicate_rows"],"download_url":meta["url"]}}
    return selected,blocked

def dependency_review(changed):
    if not changed:return []
    out={"public_intelligence_and_source_lineage_review","application_release_tests_and_visual_approval"}
    for key in changed:out.update(DEPS[key])
    return sorted(out)

def read_candidate(store,national,key,item,root):
    ident=item["identity"];prefix=weekly.PREFIX+"/care-compare/"+key+"/"+ident
    rec,_,receipt_head=ext.read_small(store,prefix+"/complete.json")
    require(rec["status"]=="COMPLETE" and rec["domain"]=="FACILITYSIGNAL_WEEKLY_CANDIDATE" and rec["policy_version"]==weekly.POLICY_VERSION and rec["key"]==key and rec["identity"]==ident and rec["public_promotion"] is False,"candidate receipt scope")
    require(rec["base_release"]==national["pointer"]["release"] and rec["base_receipt_sha256"]==national["receipt_sha256"] and rec["result"]==item["result"],"candidate receipt lineage")
    pins={f["path"]:f for f in rec["files"]}
    require(len(rec["files"])==2 and set(pins)=={"audit.json","candidate.sqlite3"},"candidate payload scope")
    for f in pins.values():require(type(f["bytes"]) is int and f["bytes"]>0 and re.fullmatch(r"[0-9a-f]{64}",f["sha256"]),"candidate payload pin")
    result=rec["result"];db_pin=pins["candidate.sqlite3"]
    require(db_pin["sha256"]==result["candidate_database_sha256"] and db_pin["bytes"]==result["candidate_database_bytes"] and db_pin["bytes"]<=archive.MAX_DB,"candidate DB bounds")
    audit,_,audit_head=ext.read_small(store,prefix+"/audit.json",pins["audit.json"]["sha256"])
    require(audit==result,"candidate audit reconciliation")
    path=root/(key+".sqlite3");head=store.head(prefix+"/candidate.sqlite3")
    ext.fetch_verified(store,prefix+"/candidate.sqlite3",db_pin,path)
    require(store.head(prefix+"/candidate.sqlite3")==head,"candidate DB changed")
    verify_inventory(store,prefix,[*pins.values(),{"path":"complete.json","bytes":receipt_head["bytes"]}],{prefix+"/audit.json":audit_head["etag"],prefix+"/candidate.sqlite3":head["etag"],prefix+"/complete.json":receipt_head["etag"]})
    return path

def release_row(db,key,pin,single):
    if single:check_integrity(db)
    r=db.execute("SELECT r.id,r.dataset,r.published_on,r.sha256,r.input_rows,r.stored_rows,r.duplicate_rows FROM current_release c JOIN releases r ON r.id=c.release_id WHERE c.dataset=?",(key,)).fetchall()
    require(len(r)==1,"source current release uniqueness")
    ident,dataset,day,digest,inputs,stored,duplicates=r[0]
    require(dataset==key and day==pin["release"] and digest==pin["sha256"] and inputs==pin["input_rows"] and stored==pin["stored_rows"] and inputs==stored+duplicates,"source release reconciliation")
    if single:
        require(db.execute("SELECT dataset FROM current_release").fetchall()==[(key,)],"single-source release scope")
        for t in ("facilities","findings"):require(not db.execute("SELECT 1 FROM "+t+" WHERE dataset<>? LIMIT 1",(key,)).fetchone(),"unrelated candidate rows")
    table="findings" if key in fs.FINDING_DATASETS else "facilities";other="facilities" if table=="findings" else "findings"
    require(db.execute("SELECT count(*) FROM "+table+" WHERE dataset=? AND release_id=?",(key,ident)).fetchone()[0]==stored and db.execute("SELECT count(*) FROM "+table+" WHERE dataset=?",(key,)).fetchone()[0]==stored,"source row reconciliation")
    require(not db.execute("SELECT 1 FROM "+other+" WHERE dataset=? LIMIT 1",(key,)).fetchone(),"source table scope")
    return ident,stored

def assemble(base_db,candidate_dbs,pins,core):
    require(set(candidate_dbs)<=set(pins)==SOURCES and not core.exists(),"scratch source scope")
    with closing(sqlite3.connect(core)) as out:
        out.executescript("""
        CREATE TABLE source_pins(dataset TEXT PRIMARY KEY,release TEXT NOT NULL,source_sha256 TEXT NOT NULL,stored_rows INTEGER NOT NULL);
        CREATE TABLE facilities(dataset TEXT NOT NULL,ccn TEXT NOT NULL,name TEXT NOT NULL,address TEXT NOT NULL,city TEXT NOT NULL,state TEXT NOT NULL,zip TEXT NOT NULL,capacity TEXT NOT NULL,PRIMARY KEY(dataset,ccn)) WITHOUT ROWID;
        CREATE TABLE citation_groups(dataset TEXT NOT NULL,ccn TEXT NOT NULL,state TEXT NOT NULL,provider_name TEXT NOT NULL,citation_rows INTEGER NOT NULL,PRIMARY KEY(dataset,ccn,state)) WITHOUT ROWID;
        """)
        for key,pin in sorted(pins.items()):
            with closing(readonly(candidate_dbs.get(key,base_db))) as db:
                ident,n=release_row(db,key,pin,key in candidate_dbs)
                if key in fs.FINDING_DATASETS:
                    out.executemany("INSERT INTO citation_groups VALUES(?,?,?,?,?)",db.execute("SELECT dataset,ccn,state,min(provider_name),count(*) FROM findings WHERE dataset=? AND release_id=? GROUP BY dataset,ccn,state",(key,ident)))
                    count=out.execute("SELECT sum(citation_rows) FROM citation_groups WHERE dataset=?",(key,)).fetchone()[0]
                else:
                    out.executemany("INSERT INTO facilities VALUES(?,?,?,?,?,?,?,?)",db.execute("SELECT dataset,ccn,name,address,city,state,zip,capacity FROM facilities WHERE dataset=? AND release_id=?",(key,ident)))
                    count=out.execute("SELECT count(*) FROM facilities WHERE dataset=?",(key,)).fetchone()[0]
                require(count==n,"scratch source count")
                out.execute("INSERT INTO source_pins VALUES(?,?,?,?)",(key,pin["release"],pin["sha256"],n))
        out.commit();check_integrity(out)
    return sha(core)

def read_json(p):return json.loads(p.read_text())
def write_json(p,o):p.write_text(json.dumps(o,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")

def project(core,pins,approved,out,changed,as_of):
    require(not out.exists(),"new preview directory")
    directory=out/"web/public-directory";directory.mkdir(parents=True)
    prior=read_json(approved/"web/public-directory/manifest.json")
    counts={};states=set();providers=citations=0;digests={}
    with closing(readonly(core)) as db:
        db.row_factory=sqlite3.Row
        for key,pin in sorted(pins.items()):
            if key in fs.FINDING_DATASETS:
                rows=[dict(r) for r in db.execute("""SELECT g.ccn,g.state,coalesce(f.name,g.provider_name) AS name,g.citation_rows
                  FROM citation_groups g LEFT JOIN facilities f ON f.dataset='nursing' AND f.ccn=g.ccn AND f.state=g.state
                  WHERE g.dataset=? ORDER BY g.state,name COLLATE NOCASE,g.ccn""",(key,))]
                n=sum(r["citation_rows"] for r in rows);citations+=n
            else:
                rows=[dict(r) for r in db.execute("SELECT ccn,name,address,city,state,zip,capacity FROM facilities WHERE dataset=? ORDER BY state,name COLLATE NOCASE,ccn",(key,))]
                n=len(rows);providers+=n;states.update(r["state"] for r in rows)
                if key=="long-term-hospital" and key not in changed:
                    original=approved/"web/public-directory/long-term-hospital.json";old=read_json(original)["records"]
                    require(sha(original)==prior["field_enrichments"][key]["projection_sha256"] and len(old)==len(rows) and all({k:v for k,v in a.items() if k!="capacity"}=={k:v for k,v in b.items() if k!="capacity"} for a,b in zip(old,rows)),"unchanged LTCH enrichment lineage")
                    rows=old
            require(n==pin["stored_rows"] and n>0,"preview count")
            path=directory/(key+".json");write_json(path,{"source":key,"release":pin["release"],"row_count":n,"records":rows})
            counts[key]={"source_rows":n,"published_records":len(rows)};digests[key]=sha(path)
    require(states==set(fs.STATES),"candidate national jurisdiction coverage")
    enriched=copy.deepcopy(prior.get("field_enrichments",{}))
    if "long-term-hospital" in changed:enriched.pop("long-term-hospital",None)
    manifest={**prior,"as_of":as_of,"source_artifact_id":None,"source_database_sha256":sha(core),"provider_rows":providers,"citation_source_rows":citations,"jurisdictions":sorted(states),"sources":counts,"field_enrichments":enriched}
    manifest["limitations"]=[*prior["limitations"],"Private preview only; dependent public evidence packs and application release tests require separate qualification."]
    write_json(directory/"manifest.json",manifest)
    # Temporary compatibility lock for market builder, never replace the historical lock.
    (out/"research").mkdir();write_json(out/LOCK,{"as_of":as_of,"sources":list(pins.values())})
    m=market.build(out)
    (out/"web/market-summary.json").write_text(json.dumps(m,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
    expected={"web/public-directory/"+k+".json" for k in SOURCES|{"manifest"}}|{"web/market-summary.json"}
    require({str(p.relative_to(out)) for p in (out/"web").rglob("*") if p.is_file()}==expected,"private preview pack scope")
    return {"provider_rows":providers,"citation_source_rows":citations,"source_counts":counts,"directory_hashes":digests,"packs":[archive.rec(k,out/k) for k in sorted(expected)],"market_rebuilt":True,"other_packs_not_emitted":["web/dialysis-service-evidence.json","web/hha-service-evidence.json","web/public-intelligence.json","web/market-boundaries.json"]}

def fetch_approved(store,national,root):
    root.mkdir()
    keys={"web/public-directory/"+k+".json" for k in SOURCES|{"manifest"}}|{"web/market-summary.json","web/hha-service-evidence.json","web/dialysis-service-evidence.json",LOCK}
    for key in sorted(keys):
        pin=national["files"][key];dest=root/key;dest.parent.mkdir(parents=True,exist_ok=True)
        require(sha(ROOT/key)==pin["sha256"],"approved baseline drift")
        ext.fetch_verified(store,national["receipt"]["payload_prefix"]+"/"+key,pin,dest)

def qualify(store,national,report,root,rehearse=False):
    lock=read_json(ROOT/LOCK);pins=source_pins(lock)
    if rehearse:changed={};blocked={};as_of=lock["as_of"]
    else:
        require(report["base_release"]==national["pointer"]["release"],"weekly archive base mismatch")
        as_of=report["checked_at"][:10];date.fromisoformat(as_of)
        changed,blocked=selection(report,pins)
    common={"base_release":national["pointer"]["release"],"base_receipt_sha256":national["receipt_sha256"],"public_promotion":False,"azure_writes":0}
    if blocked:
        ext.unchanged(store,national)
        return {**common,"status":"SOURCE_REVIEW_REQUIRED","blocked_sources":blocked,"changed_sources":sorted(changed),"preview_generated":False}
    if not changed and not rehearse:
        ext.unchanged(store,national)
        return {**common,"status":"NO_CHANGE","source_count":len(pins),"preview_generated":False,"dependent_pack_review":[]}
    approved=root/"approved";fetch_approved(store,national,approved)
    base_db,_=ext.restore_national(store,national,root/"national")
    candidates={}
    for key,item in changed.items():
        candidates[key]=read_candidate(store,national,key,item,root);pins[key]=item["source"]
    core=root/"preview-core.sqlite3";assemble(base_db,candidates,pins,core)
    out=root/"private-preview";result=project(core,pins,approved,out,set(changed),as_of)
    dependency_result=deps.qualify(out,pins,set(changed),root/"raw-dependencies",approved,rehearse)
    dialysis_result=dialysis.qualify(out,pins,set(changed),base_db,approved,report,rehearse)
    if dialysis_result is not None:dependency_result["dialysis"]=dialysis_result
    dependency_result.update(institutional.qualify(out,pins,set(changed),base_db,candidates,root/"institutional-dependencies",rehearse,report))
    verified_dependencies={k:v for k,v in dependency_result.items() if v["status"] in {"BASELINE_PARITY_PASS","PRIVATE_DEPENDENCY_QUALIFIED"}}
    if verified_dependencies:
        # Recompute downstream checksums and market summary after LTCH enrichment.
        m=market.build(out)
        (out/"web/market-summary.json").write_text(json.dumps(m,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
        allowed={p["path"] for p in result["packs"]}
        if "home-health" in verified_dependencies:
            allowed.add("web/hha-service-evidence.json")
            result["other_packs_not_emitted"].remove("web/hha-service-evidence.json")
        if "dialysis" in verified_dependencies:
            allowed.add("web/dialysis-service-evidence.json")
            result["other_packs_not_emitted"].remove("web/dialysis-service-evidence.json")
        require({str(p.relative_to(out)) for p in (out/"web").rglob("*") if p.is_file()}==allowed,"dependency preview file scope")
        result["packs"]=[archive.rec(k,out/k) for k in sorted(allowed)]
        result["directory_hashes"]={k:sha(out/"web/public-directory"/(k+".json")) for k in SOURCES}
    result["qualified_dependencies"]=verified_dependencies
    result["blocked_dependencies"]={k:v for k,v in dependency_result.items() if k not in verified_dependencies}
    parity=None
    if rehearse:
        parity=all(sha(out/"web/public-directory"/(key+".json"))==sha(approved/"web/public-directory"/(key+".json")) for key in SOURCES)
        require(parity,"baseline directory byte parity")
        old=read_json(approved/"web/market-summary.json");new=read_json(out/"web/market-summary.json")
        require(old["regions"]==new["regions"] and old["sources"]==new["sources"] and old["provider_rows"]==new["provider_rows"],"baseline market parity")
    ext.unchanged(store,national)
    return {**common,**result,"status":"BASELINE_REHEARSAL_PASS" if rehearse else "PRIVATE_PREVIEW_GENERATED_REVIEW_REQUIRED","changed_sources":sorted(changed),"preview_generated":True,"baseline_directory_byte_parity":parity,"dependent_pack_review":sorted(set(dependency_review(changed))-{v["dependency"] for v in verified_dependencies.values()}),"preview_exported":False,"source_database_sha256":sha(core)}

def main():
    p=argparse.ArgumentParser();p.add_argument("--weekly-audit",type=Path);p.add_argument("--rehearse-baseline",action="store_true");p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(bool(args.weekly_audit)!=args.rehearse_baseline and not args.receipt.exists(),"select one mode and new receipt")
    archive.run_key(os.environ);store=ReadOnlyWeeklyAzure(os.environ)
    try:
        national=ext.national_manifest(store)
        with tempfile.TemporaryDirectory(prefix="facilitysignal-private-preview-") as d:
            result=qualify(store,national,read_json(args.weekly_audit) if args.weekly_audit else None,Path(d),args.rehearse_baseline)
        with args.receipt.open("xb") as f:f.write(archive.encode(result))
        print("FACILITYSIGNAL_PRIVATE_RELEASE_PREVIEW",json.dumps(result,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
