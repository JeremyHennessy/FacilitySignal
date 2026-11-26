"""Restore an exact approved Pages pack set from private Blob, independently
rebuild directory rows from the recovered SQLite, and reconcile market data.
No deployment, public access, credentials in output, or private source export.
"""
import argparse,json,os,sqlite3,tempfile
from contextlib import closing
from pathlib import Path
import azure_national_archive as archive
from build_combined import require,sha,readonly
from scripts import azure_verified_extension as ext, audit_azure_archive_inventory as inventory
from scripts import build_market_summary as market
ROOT=Path(__file__).resolve().parents[1]
PACKS={"web/public-directory/"+x+".json" for x in ("manifest","dialysis","home-health","hospice","hospital","long-term-hospital","nursing","nursing-fire","nursing-health","rehabilitation")}|{"web/"+x+".json" for x in ("dialysis-service-evidence","hha-service-evidence","market-boundaries","market-summary","public-intelligence")}

def directory_reconcile(db_path,stage,lock):
    manifest=json.loads((stage/"web/public-directory/manifest.json").read_text())
    sources={s["key"]:s for s in lock["sources"] if s["family"]=="care-compare"}
    require(set(sources)==set(manifest["sources"]),"public source scope")
    total=cites=0
    with closing(readonly(db_path)) as db:
        db.row_factory=sqlite3.Row
        actual={r["dataset"]:r for r in db.execute("SELECT r.* FROM current_release c JOIN releases r ON r.id=c.release_id")}
        require(set(actual)==set(sources),"public release set")
        for key,s in sorted(sources.items()):
            r=actual[key]
            require(r["sha256"]==s["sha256"] and r["published_on"]==s["release"] and r["stored_rows"]==s["stored_rows"],"public source lock")
            approved=json.loads((stage/"web/public-directory"/(key+".json")).read_text())
            if key.startswith("nursing-"):
                rows=[dict(r) for r in db.execute("""SELECT d.ccn,d.state,coalesce(f.name,min(d.provider_name)) AS name,count(*) AS citation_rows
                    FROM findings d LEFT JOIN facilities f ON f.dataset='nursing' AND f.ccn=d.ccn AND f.state=d.state
                    WHERE d.dataset=? GROUP BY d.ccn,d.state,f.name ORDER BY d.state,name COLLATE NOCASE,d.ccn""",(key,))]
                n=sum(r["citation_rows"] for r in rows);cites+=n
            else:
                rows=[dict(r) for r in db.execute("SELECT ccn,name,address,city,state,zip,capacity FROM facilities WHERE dataset=? ORDER BY state,name COLLATE NOCASE,ccn",(key,))]
                n=len(rows);total+=n
            if key=="long-term-hospital" and rows!=approved["records"]:
                # Capacity is a separately qualified existing enrichment; compare every other field.
                require(len(rows)==len(approved["records"]) and all({k:v for k,v in a.items() if k!="capacity"}=={k:v for k,v in b.items() if k!="capacity"} for a,b in zip(rows,approved["records"])),"LTCH identity differs")
                require(manifest["field_enrichments"][key]["projection_sha256"]==sha(stage/"web/public-directory"/(key+".json")),"LTCH enrichment pin")
                rows=approved["records"]
            require(approved["source"]==key and approved["release"]==s["release"] and approved["row_count"]==n==s["stored_rows"] and rows==approved["records"],"directory projection differs: "+key)
            require(manifest["sources"][key]=={"source_rows":n,"published_records":len(rows)},"public manifest counts")
    require((total,cites)==(manifest["provider_rows"],manifest["citation_source_rows"]),"directory totals")
    return {"provider_rows":total,"citation_source_rows":cites,"directory_shards":len(sources)}

def stage_packs(store,output,receipt):
    require(not output.exists() and not receipt.exists(),"new stage required")
    national=ext.national_manifest(store);prefix=national["receipt"]["payload_prefix"]
    require({k for k in national["files"] if k.startswith("web/")}==PACKS,"approved pack inventory")
    with tempfile.TemporaryDirectory(prefix="private-pack-verification-") as tmp:
        root=Path(tmp);stage=root/"approved";stage.mkdir()
        for key in sorted(PACKS):
            dest=stage/key;dest.parent.mkdir(parents=True,exist_ok=True)
            pin=national["files"][key]
            require(sha(ROOT/key)==pin["sha256"],"checkout pack drift: "+key)
            ext.fetch_verified(store,prefix+"/"+key,pin,dest)
        key="research/snapshot_release_20261125.json";(stage/"research").mkdir()
        ext.fetch_verified(store,prefix+"/"+key,national["files"][key],stage/key)
        lock=json.loads((stage/key).read_text());db,_=ext.restore_national(store,national,root/"database")
        report=directory_reconcile(db,stage,lock)
        require(market.build(stage)==json.loads((stage/"web/market-summary.json").read_text()),"market summary mismatch")
        ext.unchanged(store,national)
        output.mkdir(parents=True)
        for key in sorted(PACKS):
            dest=output/key;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes((stage/key).read_bytes())
            require(sha(dest)==national["files"][key]["sha256"],"staged public pack mismatch")
        require({str(p.relative_to(output)) for p in output.rglob("*") if p.is_file()}==PACKS,"public stage scope")
        result={"status":"PASS","base_release":national["pointer"]["release"],"pack_count":len(PACKS),"bytes":sum(national["files"][k]["bytes"] for k in PACKS),"files":[national["files"][k] for k in sorted(PACKS)],"directory_reconciliation":report,"market_rebuilt":True,"existing_enrichment_pins_preserved":True,"byte_identical_approved_packs":True,"public_promotion":False,"azure_writes":0}
    with receipt.open("xb") as f:f.write(archive.encode(result))
    print("FACILITYSIGNAL_BLOB_PUBLIC_STAGE_VERIFIED",json.dumps(result,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    archive.run_key(os.environ);store=inventory.ReadOnlyAzure(os.environ)
    try:stage_packs(store,args.output,args.receipt)
    finally:store.close()
if __name__=="__main__":main()
