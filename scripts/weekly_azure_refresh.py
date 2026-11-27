"""Weekly source change detection and private candidate refresh.

The stable national and extension pointers and Pages files are read-only.
Existing private candidates may be reviewed. New Care Compare and NPPES
candidate downloads and writes are blocked pending cost and retention approval.
No automatic public promotion of inconsistent multi-source data packs.
"""
import argparse,hashlib,io,json,os,re,sqlite3,tempfile
from collections import Counter
from contextlib import closing
from datetime import date,datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import urljoin
import azure_national_archive as archive
from scripts.azure_verified_extension import national_manifest,unchanged,read_small
from scripts.azure_inventory import verify_inventory
from scripts import qualify_nppes_v2 as nppes,archive_hcris_nppes as institutional,azure_source_archive as source_archive
import collect_cms as cms
import collect_registry as registry
import facilitysignal as fs
from build_combined import require,sha,check_integrity

ROOT=Path(__file__).resolve().parents[1]
PREFIX=archive.PREFIX+"/refresh"
POLICY_VERSION=1
# No verified zero-incremental-cost capacity or release-specific retention
# approval is recorded. A future reviewed change may lift this gate; an
# environment variable or workflow dispatch must not bypass it.
WRITE_BLOCK_STATE="new_release_storage_and_reuse_review"
WRITE_BLOCK_REASON="Verified storage cost and release-specific retention approval required."
EXTRA_CMS={"nursing-penalties":"g6vv-u9sr","nursing-survey-dates":"svdt-c123","nursing-survey-summary":"tbry-pc2d"}
MAX_NEW_WEEKS=4
MAX_CHANGED_CMS=9
# Proposed conservative quarantine thresholds; not a statistical guarantee.
MIN_RATIO=0.75
MAX_RATIO=1.25
WEEKLY_LABEL=re.compile(r"NPPES Data Dissemination V\.2 - Weekly Update - ([0-9]{6})_([0-9]{6})")
KEYS=set(fs.CATALOG)|{"nppes-weekly"}

def canonical(x):
    return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
def fingerprint(x):return hashlib.sha256(canonical(x)).hexdigest()
def safe_name(name):
    pat=re.escape(PREFIX)+r"/(?:care-compare/(?:"+"|".join(re.escape(k) for k in sorted(fs.CATALOG))+r")|nppes-weekly)/[0-9a-f]{64}/(?:candidate\.sqlite3|audit\.json|complete\.json)"
    require(re.fullmatch(pat,name) is not None,"outside weekly candidate namespace")
    return name

class WeeklyAzure(source_archive.SourceAzure):
    def blob(self,name):
        if name.startswith(PREFIX+"/"):safe_name(name)
        elif name.startswith(source_archive.PREFIX+"/"):source_archive.safe(name)
        else:archive.allowed_name(name)
        return self.container.get_blob_client(name)
    def create(self,name,stream,size,kind):
        raise ValueError(WRITE_BLOCK_REASON)
    def list(self,prefix):
        if prefix.startswith(source_archive.PREFIX+"/nppes-weekly/"):
            yield from source_archive.SourceAzure.list(self,prefix);return
        safe_name(prefix+"/audit.json")
        for p in self.container.list_blobs(name_starts_with=prefix+"/",include=["metadata"]):
            yield {"name":p.name,"bytes":p.size,"etag":str(p.etag),"folder":str((p.metadata or {}).get("hdi_isfolder","")).lower()=="true"}
    def delete_probe(self,name,etag):
        raise ValueError("weekly refresh does not delete blobs")

def load_evidence():
    national=json.loads((ROOT/"research/snapshot_release_20261125.json").read_text())
    ledger=json.loads((ROOT/"research/coverage_status.json").read_text())
    pinned={x["key"]:x for x in national["sources"] if x["family"]=="care-compare"}
    require(set(pinned)==set(fs.CATALOG),"Care Compare coverage")
    extra={"nursing-penalties":ledger["cms_penalties_qualified_baseline"]["audit"],
           "nursing-survey-dates":ledger["nursing_survey_qualified_baselines"]["dates"]["audit"],
           "nursing-survey-summary":ledger["nursing_survey_qualified_baselines"]["summary"]["audit"]}
    return national,ledger,pinned,extra

def release_state(meta,count,old):
    require(type(count) is int and count>0,"invalid publisher count")
    new=date.fromisoformat(meta["released"]);previous=date.fromisoformat(old["release"])
    require(new<=datetime.now(timezone.utc).date(),"future publisher release")
    if new<previous:return "older_release_review"
    if new==previous:
        return "unchanged" if meta["url"]==old["download_url"] and count==old["input_rows"] else "same_date_revision_review"
    if not MIN_RATIO<=count/old["input_rows"]<=MAX_RATIO:return "count_change_review"
    return "new_release"

def cms_key(key,meta,count):
    return fingerprint({"policy":POLICY_VERSION,"key":key,"publisher":meta,"api_count":count})
def existing(store,prefix,key,identity):
    name=prefix+"/complete.json"
    if not store.exists(name):return None
    receipt,_,_=read_small(store,name)
    require(receipt["status"]=="COMPLETE" and receipt["domain"]=="FACILITYSIGNAL_WEEKLY_CANDIDATE" and receipt["key"]==key and receipt["identity"]==identity and receipt["policy_version"]==POLICY_VERSION,"existing candidate receipt mismatch")
    expected={"audit.json"} if key=="nppes-weekly" else {"audit.json","candidate.sqlite3"}
    require({r["path"] for r in receipt["files"]}==expected and len(receipt["files"])==len(expected),"candidate inventory")
    for r in receipt["files"]:
        safe_name(prefix+"/"+r["path"])
        require(store.head(prefix+"/"+r["path"])["bytes"]==r["bytes"],"candidate payload size changed")
        require(re.fullmatch(r"[0-9a-f]{64}",r["sha256"]) is not None,"candidate pin")
        # Audit is small; verify it every week. Database receipt is validated
        # on creation and again before any later public promotion/restore.
        if r["path"]=="audit.json":read_small(store,prefix+"/"+r["path"],r["sha256"])
    return receipt

def publish_candidate(store,prefix,key,identity,files,result,national):
    unchanged(store,national)
    records=[archive.rec(p,f) for p,f in sorted(files.items())]
    require(not store.exists(prefix+"/complete.json"),"candidate already exists")
    etags={}
    for r in records:
        name=prefix+"/"+r["path"];safe_name(name)
        # Resume an incomplete upload only if its bytes already match exactly.
        if not store.exists(name):
            with files[r["path"]].open("rb") as f:
                store.create(name,f,r["bytes"],"application/json" if name.endswith(".json") else "application/octet-stream")
        etags[name]=archive.verify(store,name,r)
    verify_inventory(store,prefix,records,etags)
    receipt={"format_version":1,"status":"COMPLETE","domain":"FACILITYSIGNAL_WEEKLY_CANDIDATE",
             "policy_version":POLICY_VERSION,"key":key,"identity":identity,
             "base_release":national["pointer"]["release"],"base_receipt_sha256":national["receipt_sha256"],
             "files":records,"result":result,"public_promotion":False}
    unchanged(store,national)
    archive.put_bytes(store,prefix+"/complete.json",archive.encode(receipt))
    return receipt

def qualify_cms_candidate(key,meta,count,root):
    item=cms.download(key,root)
    require(item["metadata"]==meta and item["expected_rows"]==count,"publisher changed since detection")
    db=root/"candidate.sqlite3"
    result=fs.import_csv(db,key,item["path"],meta["released"],count)
    require(result["status"]=="imported" and result["input_rows"]==count and result["stored_rows"]+result["duplicate_rows"]==count and result["sha256"]==item["sha256"],"import reconciliation")
    with closing(fs.connect(db)) as conn:
        check_integrity(conn)
        table="findings" if key in fs.FINDING_DATASETS else "facilities"
        require(conn.execute("SELECT count(*) FROM "+table+" WHERE dataset=?",(key,)).fetchone()[0]==result["stored_rows"],"candidate row count")
        require(conn.execute("SELECT count(*) FROM current_release").fetchone()[0]==1,"candidate release count")
        require(conn.execute("SELECT count(DISTINCT state) FROM "+table).fetchone()[0]>=50,"national coverage exception")
    require(sha(item["path"])==item["sha256"],"source bytes changed")
    # Duplicate counts are kept at source grain, not inferred site identity.
    return {"publisher":meta,"api_count":count,"source_sha256":item["sha256"],"source_bytes":item["bytes"],"columns":len(item["columns"]),"import":result,"candidate_database_sha256":sha(db),"candidate_database_bytes":db.stat().st_size,"integrity":"passed","scope":"Single-source private refresh candidate; dependent national/public packs not rebuilt."},db

def discover_nppes(html):
    p=nppes.Links();p.feed(html);p.close()
    weeks={};monthly=[]
    for href,label in p.links:
        m=WEEKLY_LABEL.fullmatch(label)
        is_monthly=label.startswith("NPPES Data Dissemination V.2 (") and label.endswith(")")
        if not m and not is_monthly:continue
        url=nppes.allowed(urljoin(nppes.PAGE,href))
        require(url.lower().endswith(".zip"),"NPPES archive link")
        if m:
            start,end=(datetime.strptime(s,"%m%d%y").date() for s in m.groups())
            require(end-start==timedelta(days=6) and start.weekday()==0 and end<=datetime.now(timezone.utc).date(),"NPPES week shape")
            require(label not in weeks or weeks[label]["url"]==url,"ambiguous weekly archive")
            weeks[label]={"label":label,"url":url,"start":start.isoformat(),"end":end.isoformat()}
        elif is_monthly:monthly.append({"label":label,"url":url})
    require(0<len(weeks)<=8 and len(monthly)==1,"NPPES index coverage")
    return sorted(weeks.values(),key=lambda x:x["start"]),monthly[0]

def qualify_nppes_week(week,root,store,national):
    path=root/"source.zip"
    meta=nppes.download(path,"weekly",publisher_label=week["label"])
    require(meta["url"]==week["url"],"NPPES weekly distribution changed")
    prior=source_archive.existing(store,"nppes-weekly",meta["sha256"])
    if prior is None:
        db=root/"projection.sqlite3";summary=institutional.nppes_project(path,db,"weekly")
        path.unlink()
        audit={"release":week,"publisher":meta,"summary":summary,"projection_sha256":sha(db),"projection_bytes":db.stat().st_size,"reuse_review":"pending","public_promotion":False}
        prior=source_archive.publish(store,"nppes-weekly",meta,db,audit,root,national)
    require(prior["summary"]["organization_observations"]>0 and prior["summary"]["individual_identifiers_retained"]==0,"institutional archive scope")
    return {"release":week,"publisher":meta,"archive_release":prior["payload_prefix"],"archive_source_sha256":meta["sha256"],"organization_observations":prior["summary"]["organization_observations"],"taxonomy_observations":prior["summary"]["taxonomy_observations"],"scope":"Private organization-only weekly projection; not applied to monthly registry.","public_promotion":False}

def discover_registry(catalog,sources):
    # Discover latest version metadata without fetching large registry or
    # ownership files; their qualified adapters remain explicitly pinned.
    out={}
    for old in sources:
        if old["family"] not in {"registry","pecos"}:continue
        prior=old["metadata"];matches=[d for d in catalog.get("dataset",[]) if d.get("title")==prior["title"] and d.get("accessLevel")=="public"]
        require(len(matches)==1,"registry catalog identity")
        dist=matches[0].get("distribution",[])
        latest=[x for x in dist if x.get("format")=="API" and x.get("description")=="latest"]
        require(len(latest)==1 and latest[0].get("temporal"),"ambiguous latest registry release")
        period=latest[0]["temporal"]
        versions=[registry.allowed(x["accessURL"]) for x in dist if x.get("format")=="API" and x.get("description")!="latest" and x.get("temporal")==period and x.get("accessURL")]
        require(len(versions)==1,"registry version ambiguity")
        out[old["key"]]={"period":period,"version_api":versions[0],"state":"unchanged" if period==prior["period"] and versions[0]==prior["api"] else "new_version_review"}
    return out

def run(store,national,root):
    lock,ledger,pinned,extra=load_evidence()
    results={};failures=[]
    for key,old in sorted(pinned.items()):
        try:
            ident=fs.CATALOG[key][0];meta=cms.metadata(ident);n=cms.count(ident)
            state=release_state(meta,n,old)
            report={"publisher":meta,"api_count":n,"state":state,"published_baseline_release":old["release"]}
            if state=="new_release":
                identity=cms_key(key,meta,n);prefix=PREFIX+"/care-compare/"+key+"/"+identity
                old_candidate=existing(store,prefix,key,identity)
                if old_candidate:
                    report.update(state="candidate_already_qualified",candidate=old_candidate["result"])
                else:
                    report.update(state=WRITE_BLOCK_STATE,candidate_identity=identity,reason=WRITE_BLOCK_REASON)
            results[key]=report
        except Exception as e:
            results[key]={"state":"failed","error_type":type(e).__name__};failures.append(key)
    for key,old in extra.items():
        try:
            meta=cms.metadata(EXTRA_CMS[key]);n=cms.count(EXTRA_CMS[key])
            state=release_state(meta,n,{"release":old["publisher"]["released"],"download_url":old["publisher"]["url"],"input_rows":old["input_rows"]})
            results[key]={"publisher":meta,"api_count":n,"state":"new_release_review" if state=="new_release" else state}
        except Exception as e:results[key]={"state":"failed","error_type":type(e).__name__};failures.append(key)
    try:
        with nppes.response(nppes.PAGE) as res:
            page=res.read(5_000_001);require(0<len(page)<=5_000_000,"NPPES index bound")
        weeks,monthly=discover_nppes(page.decode("utf-8",errors="strict"))
        known={v["audit"]["publisher_label"]:v["audit"]["publisher"]["url"] for v in ledger["nppes_v2_qualified_baselines"].values()}
        report=[]
        for week in weeks:
            if known.get(week["label"])==week["url"]:
                report.append({**week,"state":"previously_qualified"});continue
            if week["label"] in known:
                report.append({**week,"state":"same_label_revision_review"});continue
            identity=fingerprint({"policy":POLICY_VERSION,"release":week,"private_projection":1});prefix=PREFIX+"/nppes-weekly/"+identity
            prior=existing(store,prefix,"nppes-weekly",identity)
            if prior:report.append({**week,"state":"candidate_already_qualified","organization_observations":prior["result"]["organization_observations"]});continue
            report.append({**week,"state":WRITE_BLOCK_STATE,"candidate_identity":identity,"reason":WRITE_BLOCK_REASON})
        results["nppes"]={"weeks":report,"monthly":{**monthly,"state":"unchanged" if known.get(monthly["label"])==monthly["url"] else "new_monthly_release_review"}}
    except Exception as e:results["nppes"]={"state":"failed","error_type":type(e).__name__};failures.append("nppes")
    try:results["registry_and_ownership"]=discover_registry(registry.get_json(registry.CATALOG),lock["sources"])
    except Exception as e:results["registry_and_ownership"]={"state":"failed","error_type":type(e).__name__};failures.append("registry_and_ownership")
    try:
        from scripts.weekly_archive_monitor import monitor
        extra_archive=monitor(store,national)
        results["additional_private_archives"]=extra_archive
        failures.extend("archive:"+k for k,v in extra_archive.items() if v["state"]=="failed")
    except Exception as e:
        results["additional_private_archives"]={"state":"failed","error_type":type(e).__name__}
        failures.append("additional_private_archives")
    unchanged(store,national)
    return {"format_version":1,"checked_at":datetime.now(timezone.utc).isoformat(),"base_release":national["pointer"]["release"],"policy_version":POLICY_VERSION,"sources":results,"failed_checks":failures,"national_pointer_unchanged":True,"pages_packs_unchanged":True,"public_promotion":False,"new_candidate_writes_enabled":False,"write_block_reason":WRITE_BLOCK_REASON,"limits":"Discovery and read-only verification of existing Care Compare and NPPES weekly candidates. New candidate downloads and writes blocked pending verified storage cost and release-specific retention approval. Nursing supplementary, registry/ownership and monthly NPPES changes detected for separate qualification; not automatic public release. Source metadata equality does not prove unchanged bytes at mutable URLs."}

def main():
    p=argparse.ArgumentParser();p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    archive.run_key(os.environ)
    store=WeeklyAzure(os.environ)
    try:
        national=national_manifest(store)
        with tempfile.TemporaryDirectory(prefix="weekly-refresh-") as d:
            result=run(store,national,Path(d))
        with a.audit.open("x") as f:json.dump(result,f,indent=2);f.write("\n")
        print("FACILITYSIGNAL_WEEKLY_REFRESH",json.dumps(result,sort_keys=True),flush=True)
        require(not result["failed_checks"],"weekly source checks incomplete")
    finally:store.close()
if __name__=="__main__":main()
