"""Acquire new hospice ownership and selected HHA financial sources in Azure.

Use current, explicit publisher version and independent counts. Do not retain
individual owner rows, contacts, names/addresses from financial reports, or raw
source files. HHA report keys may be compared with the archived detailed report
index, not assumed to refer to identical report versions or physical sites.
"""
import argparse,csv,hashlib,io,json,os,re,sqlite3,tempfile
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
import azure_national_archive as a
import collect_registry as registry
import collect_ownership as ownership
from probe_ownership import select
from scripts import azure_source_archive as storemod,azure_verified_extension as ext
from scripts import qualify_hospital_cost as cost
from build_combined import require,sha,readonly,check_integrity
ROOT=Path(__file__).resolve().parents[1]
HCRIS_SHA="d3bf63b5d6293aa98f5a1cee096858c5d32d322f3cbe8471d9b6d410b37182d6"
HHA_MEASURES=["Skilled Nursing Care-RN, Medicare Title XVIII Visits","Total, Medicare Title XVIII Visits","Skilled Nursing Care-LPN, Medicare Title XVIII Visits","Physical Therapy, Medicare Title XVIII Visits"]
TARGETS={"hospice":("Hospice All Owners","2026-10-01/2026-12-31","hospice-organizational-ownership"),"hha-cost":("Home Health Agency Cost Report","2024-01-01/2024-12-31","hha-selected-cost-2024")}
def selection(catalog,key):
    title,period,_=TARGETS[key];meta=select(catalog,title)
    require(meta["period"]==period and re.fullmatch(r"https://data\.cms\.gov/data-api/v1/dataset/[0-9a-f-]{36}/data",meta["api"]),"publisher version or period changed")
    require(len(meta["distributions"])==1 and meta["distributions"][0]["format"]=="CSV","CSV distribution scope")
    return {**meta,"url":meta["distributions"][0]["url"],"zipped":False}
def fetch(meta,path,max_bytes):
    h=hashlib.sha256();size=0
    with registry.response(meta["url"],"text/csv") as res,path.open("xb") as out:
        require(res.geturl()==meta["url"],"unexpected publisher redirect")
        while chunk:=res.read(1024*1024):
            size+=len(chunk);require(size<=max_bytes,"source size bound")
            h.update(chunk);out.write(chunk)
    require(size>0 and sha(path)==h.hexdigest(),"source hash")
    return h.hexdigest(),size
def hospice_project(path,db_path,meta,digest,n,api_fields):
    with closing(sqlite3.connect(db_path)) as db:
        ownership.init(db);result=ownership.ingest(db,"hospice-owner",meta,path,digest,n)
        require(len(result["columns"])==len(set(api_fields)) and set(result["columns"])==set(api_fields),"CSV/API schema mismatch")
        require(result["stored_rows"]>0 and result["stored_rows"]+result["excluded_individual_rows"]==n==result["input_rows"] and result["rejected_rows"]==0,"owner reconciliation")
        require(not result["identifier_quality_flags"],"owner identifier exceptions")
        require(all(set(json.loads(x[0]))==set(ownership.ORG) for x in db.execute("SELECT projection FROM pecos_org_role_rows")),"institutional projection scope")
        check_integrity(db)
        roles=dict(db.execute("SELECT role_code,count(*) FROM pecos_org_role_rows GROUP BY role_code"))
        require(sum(roles.values())==result["stored_rows"],"role count")
        return {"source_id":"FS-050","input_rows":n,"organization_role_rows":result["stored_rows"],"excluded_individual_rows":result["excluded_individual_rows"],"rejected_rows":0,"individual_rows_retained":0,"source_columns":len(api_fields),"role_code_counts":roles,"distinct_enrollment_ids":db.execute("SELECT count(DISTINCT enrollment_id) FROM pecos_org_role_rows").fetchone()[0],"distinct_owner_pac_ids":db.execute("SELECT count(DISTINCT owner_pac_id) FROM pecos_org_role_rows").fetchone()[0],"public_promotion":False,"limits":"Self-reported organizational roles only; no physical property ownership or enrollment linkage inference."}
def restore_hcris(store,root,national):
    prefix=storemod.prefix_for("hcris-hha-2024",HCRIS_SHA)
    rec,_,_=ext.read_small(store,prefix+"/complete.json")
    require(rec["status"]=="COMPLETE" and rec["domain"]=="FACILITYSIGNAL_PRIVATE_SOURCE" and rec["key"]=="hcris-hha-2024" and rec["source_sha256"]==HCRIS_SHA and rec["base_receipt_sha256"]==national["receipt_sha256"],"HCRIS source receipt")
    pin=next(x for x in rec["files"] if x["path"]=="projection.sqlite3")
    require(0<pin["bytes"]<=storemod.MAX_DB,"HCRIS projection bound")
    db=root/"hcris.sqlite3";ext.fetch_verified(store,prefix+"/files/projection.sqlite3",pin,db)
    with closing(readonly(db)) as conn:
        check_integrity(conn)
        require(conn.execute("SELECT count(*) FROM reports").fetchone()[0]==11009,"HCRIS report key count")
    return db,pin
def hha_cost_project(data,n,api_fields,db_path,providers,hcris):
    with closing(sqlite3.connect(db_path)) as db:
        result=cost.project(data,n,len(api_fields),api_fields,db,providers,measures=HHA_MEASURES)
        require(result["stored_rows"]==n and result["rejected_rows"]==result["exact_duplicate_rows"]==result["unambiguous_period_order_anomalies"]==0,"cost report anomalies")
        require(not any(v.get("unrecognized",0) for v in result["measure_value_states"].values()),"numeric measure exceptions")
        require(not any(v for k,v in result["fiscal_date_shape_counts"].items() if k.endswith(("_invalid","_unrecognized"))),"fiscal date exceptions")
        db.execute("ATTACH DATABASE ? AS detail",(hcris.resolve().as_uri()+"?mode=ro",))
        db.execute("CREATE TABLE hcris_report_candidates(report_key TEXT PRIMARY KEY REFERENCES cost_report(report_key),state TEXT NOT NULL)")
        db.execute("INSERT INTO hcris_report_candidates SELECT r.report_key,CASE WHEN EXISTS(SELECT 1 FROM detail.reports d WHERE d.report_key=r.report_key) THEN 'exact_report_key' ELSE 'unmatched_report_key' END FROM cost_report r")
        db.commit()
        links=dict(db.execute("SELECT state,count(*) FROM hcris_report_candidates GROUP BY state"))
        require(sum(links.values())==n,"report crosswalk reconciliation")
        db.execute("DETACH DATABASE detail")
        check_integrity(db)
        return {**result,"source_id":"FS-055","scope":"Selected HHA FY2024 report projection; separate HCRIS subrelease","hcris_exact_report_key_candidates":links,"projected_measure_names":HHA_MEASURES,"public_promotion":False,"limits":"Historical visit observations by report. Exact report-key and CCN/state matches are evidence candidates only; no inference of current demand or unique sites."}
def main():
    p=argparse.ArgumentParser();p.add_argument("--source",choices=TARGETS,required=True);p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ);store=storemod.SourceAzure(os.environ)
    try:
        national=storemod.national_manifest(store);meta=selection(registry.get_json(registry.CATALOG),args.source)
        n=registry.expected_rows(meta)
        require(0<n<=(200000 if args.source=="hospice" else 100000),"version count bound")
        sample=registry.get_json(meta["api"]+"?size=1")
        require(isinstance(sample,list) and len(sample)==1 and isinstance(sample[0],dict),"API schema sample")
        fields=list(sample[0]);require(0<len(fields)<=300,"column bound")
        needed=ownership.ORG+("TYPE - OWNER",) if args.source=="hospice" else tuple(cost.CORE+HHA_MEASURES)
        require({x.casefold() for x in needed}<={x.casefold() for x in fields},"required publisher fields absent")
        with tempfile.TemporaryDirectory(prefix="postacute-source-") as d:
            root=Path(d);source=root/"source.csv";digest,size=fetch(meta,source,80_000_000)
            require(selection(registry.get_json(registry.CATALOG),args.source)==meta and registry.expected_rows(meta)==n,"publisher changed during retrieval")
            publisher={**meta,"sha256":digest,"bytes":size};key=TARGETS[args.source][2];receipt=storemod.existing(store,key,digest)
            if receipt is None:
                db=root/"projection.sqlite3"
                if args.source=="hospice":summary=hospice_project(source,db,meta,digest,n,fields)
                else:
                    hcris,pin=restore_hcris(store,root,national)
                    # Use the previously approved Care Compare HHA directory
                    # bytes, and independently verify the archived copy.
                    pack="web/public-directory/home-health.json";local=ROOT/pack;expected=national["files"][pack]
                    require(sha(local)==expected["sha256"],"HHA directory pack drift")
                    a.verify(store,national["receipt"]["payload_prefix"]+"/"+pack,expected)
                    providers={}
                    for row in json.loads(local.read_text())["records"]:providers.setdefault(row["ccn"],set()).add(row["state"])
                    summary=hha_cost_project(source.read_bytes(),n,fields,db,providers,hcris)
                    require(sha(hcris)==pin["sha256"],"HCRIS base changed")
                    summary["hcris_projection_sha256"]=pin["sha256"]
                require(sha(source)==digest,"source mutated")
                source.unlink()
                audit={"publisher":publisher,"summary":summary,"projection_sha256":sha(db),"projection_bytes":db.stat().st_size,"reuse_review":"pending","public_promotion":False}
                receipt=storemod.publish(store,key,publisher,db,audit,root,national)
        args.receipt.write_bytes(a.encode(receipt))
        print("PRIVATE_POSTACUTE_SOURCE_COMPLETE",args.source,json.dumps(receipt,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
