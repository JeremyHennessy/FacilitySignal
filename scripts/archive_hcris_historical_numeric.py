"""Archive all remaining annual numeric members against exact completed indexes.

One publisher download per form. Process bounded nonoverlapping year groups,
reconcile each group against the existing report index, then archive it with
an immutable receipt. The verified FY2024 supplemental archive is excluded.
"""
import argparse,json,os,tempfile
from pathlib import Path
import azure_national_archive as a
from build_combined import require,sha
from scripts import archive_hcris_form_indexes as forms,archive_hcris_numeric_partitions as numeric
from scripts import azure_source_archive as storage,audit_azure_archive_inventory as inventory,azure_verified_extension as ext
ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/"research/hcris_historical_numeric_plan_20261126.json"

def validate_plan(form,plan,prior):
    require(plan["format_version"]==1 and plan["excluded_year"]=="2024" and plan["max_rows_per_group"]==3500000,"historical plan version")
    item=plan["forms"][form];annual=prior["annual_partitions"]
    counts={y:p["child_tables"]["numeric"]["rows"] for y,p in annual.items() if y!="2024"}
    require(counts==item["source_year_counts"] and "2024" in annual,"historical year/count drift")
    all_years=[]
    for g in item["groups"]:
        years=g["years"];key=g["key"]
        require(years and years==sorted(years) and len(years)==len(set(years)) and set(years)<=set(counts),"historical group years")
        require(years==storage.HISTORICAL_NUMERIC_YEARS[key] and storage.SUPPLEMENTAL_NUMERIC_PARENTS[key]==item["parent"],"immutable group scope")
        require(g["rows"]==sum(counts[y] for y in years) and 0<g["rows"]<=plan["max_rows_per_group"],"historical group rows")
        all_years.extend(years)
    require(len(all_years)==len(set(all_years)) and set(all_years)==set(counts),"historical groups overlap or omit years")
    return item

def validate_receipt(rec,group,item,db_pin):
    s=rec["summary"]
    require(rec["status"]=="COMPLETE" and rec["key"]==group["key"] and rec["source_sha256"]==item["source_sha256"] and rec["sha256_readback"] is True and rec["public_promotion"] is False,"historical receipt identity")
    require(s["source_index_key"]==item["parent"] and s["source_index_sha256"]==db_pin["sha256"] and s["source_index_publisher_sha256"]==item["source_sha256"] and sorted(s["annual_partitions"])==group["years"],"historical receipt scope")
    require(s["input_numeric_rows"]==group["rows"]==sum(s[k] for k in ("stored_rows","unresolved_parent_rows","coordinate_review_rows","numeric_syntax_review_rows")) and s["stored_rows"]==s["supplemental_numeric_rows"] and s["alpha_values_retained"]==0,"historical receipt accounting")
    require(all(p["input_numeric_rows"]==item["source_year_counts"][y] for y,p in s["annual_partitions"].items()),"historical receipt per-year counts")

def main():
    p=argparse.ArgumentParser();p.add_argument("--source",choices=("fqhc","hospice","renal"),required=True);p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ)
    form=args.source;plan=json.loads(PLAN.read_text());item=plan["forms"][form];parent=item["parent"]
    ledger=json.loads(inventory.LEDGER.read_text());pins=[p for p in ledger["receipts"] if p["key"]==parent and p["kind"]=="publisher"]
    require(len(pins)==1 and pins[0]["source_sha256"]==item["source_sha256"],"exact parent index pin")
    pin=pins[0];db_pin=next(f for f in pin["files"] if f["path"]=="projection.sqlite3")
    store=storage.SourceAzure(os.environ)
    try:
        national=storage.national_manifest(store);rec=storage.existing(store,parent,pin["source_sha256"])
        require(rec is not None,"parent index absent");inventory.source_matches(rec,pin,national)
        prior=rec["summary"];publisher=rec["publisher"];item=validate_plan(form,plan,prior)
        # Verify the excluded FY2024 archive exists and still matches its original parent.
        existing_2024=storage.existing(store,f"hcris-{form}-2024-numeric",pin["source_sha256"])
        require(existing_2024 is not None and set(existing_2024["summary"]["annual_partitions"])=={"2024"} and existing_2024["summary"]["source_index_sha256"]==db_pin["sha256"],"FY2024 exclusion lineage")
        existing={g["key"]:storage.existing(store,g["key"],pin["source_sha256"]) for g in item["groups"]}
        results=[]
        with tempfile.TemporaryDirectory(prefix="hcris-historical-numeric-") as d:
            root=Path(d);source=root/"source.zip";index_db=root/"index.sqlite3";meta=None
            if not all(existing.values()):
                observed=forms.discover(form);require(observed["url"]==publisher["url"],"publisher link drift")
                meta=forms.download(observed,source)
                require(meta["sha256"]==pin["source_sha256"] and meta["bytes"]==publisher["bytes"] and sha(source)==pin["source_sha256"] and forms.discover(form)==observed,"publisher byte/link drift")
                ext.fetch_verified(store,rec["payload_prefix"]+"/projection.sqlite3",db_pin,index_db)
            for group in item["groups"]:
                key=group["key"];result=existing[key]
                if result is None:
                    with tempfile.TemporaryDirectory(prefix="year-group-",dir=root) as part:
                        work=Path(part);out=work/"projection.sqlite3"
                        summary=numeric.project(source,index_db,out,prior,tuple(group["years"]))
                        require(summary["input_numeric_rows"]==group["rows"],"group source row drift")
                        require(sha(index_db)==db_pin["sha256"],"report index mutated")
                        summary.update({"source_index_key":parent,"source_index_sha256":db_pin["sha256"],"source_index_publisher_sha256":pin["source_sha256"]})
                        pub={**meta,"kind":"supplemental_numeric_projection","source_index_key":parent,"selected_years":group["years"]}
                        audit={"publisher":pub,"summary":summary,"projection_sha256":sha(out),"projection_bytes":out.stat().st_size,"reuse_review":"pending","public_promotion":False}
                        result=storage.publish(store,key,pub,out,audit,work,national)
                validate_receipt(result,group,item,db_pin);results.append(result)
                print("PRIVATE_HCRIS_HISTORICAL_NUMERIC_GROUP_COMPLETE",form,json.dumps(result,sort_keys=True),flush=True)
            if meta is not None:require(sha(source)==pin["source_sha256"],"source mutated during partitioning")
        ext.unchanged(store,national)
        summary={"status":"COMPLETE","form":form,"source_sha256":item["source_sha256"],"source_index_key":parent,"source_index_sha256":db_pin["sha256"],"input_numeric_rows":sum(g["rows"] for g in item["groups"]),"stored_rows":sum(r["summary"]["stored_rows"] for r in results),"unresolved_parent_rows":sum(r["summary"]["unresolved_parent_rows"] for r in results),"coordinate_review_rows":sum(r["summary"]["coordinate_review_rows"] for r in results),"numeric_syntax_review_rows":sum(r["summary"]["numeric_syntax_review_rows"] for r in results),"groups":len(results),"years":sorted(item["source_year_counts"]),"payload_bytes":sum(r["total_bytes"] for r in results),"public_promotion":False,"all_group_sha256_readback":True}
        require(summary["input_numeric_rows"]==sum(summary[k] for k in ("stored_rows","unresolved_parent_rows","coordinate_review_rows","numeric_syntax_review_rows")),"form accounting")
        with args.receipt.open("xb") as f:f.write(a.encode({**summary,"receipts":results}))
        print("PRIVATE_HCRIS_HISTORICAL_NUMERIC_COMPLETE",form,json.dumps(summary,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
