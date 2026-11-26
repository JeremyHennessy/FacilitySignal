"""Stream one pinned FY2024 HCRIS numeric member into disjoint ordinal shards.

All shards are locally reconciled against the entire original index before any
upload. Preserve exact decimal text, source ordinal and bounded coordinates.
Unmatched or unreviewed values remain excluded and explicitly accounted for.
No alpha text, interpreted measure semantics, or public publication.
"""
import argparse,csv,io,json,os,re,sqlite3,tempfile,zipfile
from collections import Counter
from contextlib import closing
from pathlib import Path
import azure_national_archive as a
from build_combined import require,sha,readonly,check_integrity
from scripts import archive_hcris_form_indexes as forms,qualify_hcris_hha as h
from scripts import azure_source_archive as storage,audit_azure_archive_inventory as inventory,azure_verified_extension as ext
MAX_DB=350_000_000
BATCH=10000

def scope_plan(form):
    return [(key,start,end) for key,(f,start,end) in storage.LARGE_NUMERIC_SCOPES.items() if f==form]

def validate_plan(plan,total):
    require(plan and len({key for key,_,_ in plan})==len(plan),"partition keys")
    last=0
    for key,start,end in plan:
        require(start==last+1 and start<=end<=total and end-start+1<=storage.LARGE_NUMERIC_PART_SIZE,"partition coverage")
        last=end
    require(last==total,"incomplete ordinal coverage")

def load_parents(z,roles,index_db,prior):
    with closing(readonly(index_db)) as idx:
        check_integrity(idx)
        index={key:(ordinal,numeric,alpha) for key,ordinal,numeric,alpha in idx.execute("SELECT report_key,ordinal,numeric_rows,alpha_rows FROM reports")}
    require(len(index)==prior["stored_rows"],"report index count")
    seen=set();widths=Counter()
    with z.open(roles["report"]) as raw,io.TextIOWrapper(raw,encoding="latin-1",newline="") as f:
        for ordinal,row in enumerate(csv.reader(f,strict=True),1):
            require(ordinal<=150000 and 2<=len(row)<=100,"report row shape")
            key=h.report_key(row[0])
            require(key in index and key not in seen and index[key][0]==ordinal,"report key or ordinal drift")
            seen.add(key);widths[str(len(row))]+=1
    require(seen==set(index) and dict(widths)==prior["report_width_counts"],"report source/index mismatch")
    return index

def build_shard(root,key,start,end,reader,index,global_counts,year="2024"):
    folder=root/key;folder.mkdir()
    path=folder/"projection.sqlite3";stats=Counter();shapes=Counter();values=Counter();states=Counter()
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
        CREATE TABLE report_references(source_year TEXT NOT NULL,report_key TEXT NOT NULL,PRIMARY KEY(source_year,report_key)) WITHOUT ROWID;
        CREATE TABLE numeric_cells(source_year TEXT NOT NULL,ordinal INTEGER NOT NULL,report_key TEXT NOT NULL,worksheet TEXT NOT NULL,line TEXT NOT NULL,col TEXT NOT NULL,value_text TEXT NOT NULL,value_state TEXT NOT NULL,PRIMARY KEY(source_year,ordinal),FOREIGN KEY(source_year,report_key) REFERENCES report_references(source_year,report_key)) WITHOUT ROWID;
        """)
        parents=set();batch=[]
        for ordinal in range(start,end+1):
            row=next(reader,None)
            require(row is not None and len(row)==5,"numeric child row width or early EOF")
            ident=h.report_key(row[0]);w,l,c=(v.strip() for v in row[1:4]);value=row[4].strip()
            bounded=bool(re.fullmatch(r"[A-Z0-9*]{1,7}",w) and re.fullmatch(r"[0-9A-Z]{1,5}",l) and re.fullmatch(r"[0-9A-Z]{1,5}",c))
            state=h.cell_state(value)
            shapes["bounded_source_coordinate" if bounded else "coordinate_review"]+=1;values[state]+=1
            if ident not in index:
                stats["unresolved_parent"]+=1;continue
            global_counts[ident]+=1
            if not bounded:stats["coordinate_review"]+=1;continue
            if state=="unrecognized":stats["numeric_syntax_review"]+=1;continue
            if ident not in parents:
                db.execute("INSERT INTO report_references VALUES(?,?)",(year,ident));parents.add(ident)
            stats["retained"]+=1;states[state]+=1;batch.append((year,ordinal,ident,w,l,c,value,state))
            if len(batch)>=BATCH:
                db.executemany("INSERT INTO numeric_cells VALUES(?,?,?,?,?,?,?,?)",batch);batch.clear()
                require(db.execute("PRAGMA page_count").fetchone()[0]*db.execute("PRAGMA page_size").fetchone()[0]<=MAX_DB,"partition storage budget")
        if batch:db.executemany("INSERT INTO numeric_cells VALUES(?,?,?,?,?,?,?,?)",batch)
        db.execute("CREATE INDEX numeric_report_lookup ON numeric_cells(source_year,report_key)")
        db.commit();check_integrity(db)
        require(0<path.stat().st_size<=MAX_DB,"partition final size")
        actual=db.execute("SELECT count(*),min(ordinal),max(ordinal) FROM numeric_cells").fetchone()
        require(actual[0]==stats["retained"]>0 and start<=actual[1]<=actual[2]<=end,"stored ordinal scope")
        require(sum(stats.values())==sum(shapes.values())==sum(values.values())==end-start+1,"partition row accounting")
        require(dict(db.execute("SELECT value_state,count(*) FROM numeric_cells GROUP BY value_state"))==dict(states),"stored state reconciliation")
    return {"path":path,"key":key,"summary":{"stored_rows":stats["retained"],"supplemental_numeric_rows":stats["retained"],"source_year":year,"ordinal_start":start,"ordinal_end":end,"input_numeric_rows":end-start+1,"unresolved_parent_rows":stats["unresolved_parent"],"coordinate_review_rows":stats["coordinate_review"],"numeric_syntax_review_rows":stats["numeric_syntax_review"],"source_coordinate_shapes":dict(shapes),"source_value_states":dict(values),"retained_value_states":dict(states),"report_references_not_counted":len(parents),"alpha_values_retained":0,"new_publisher_release":False,"units_interpreted":False,"public_promotion":False}}

def project(source,index_db,prior,plan,root):
    num=prior["child_tables"]["numeric"];total=num["rows"];validate_plan(plan,total)
    with zipfile.ZipFile(source) as z:
        roles=forms.members(z)
        require(roles["numeric"].file_size==num["uncompressed_bytes"] and format(roles["numeric"].CRC,"08x")==num["zip_crc32"],"numeric member pin")
        index=load_parents(z,roles,index_db,prior)
        global_counts=Counter();shapes=Counter();values=Counter();results=[]
        with z.open(roles["numeric"]) as raw,io.TextIOWrapper(raw,encoding="latin-1",newline="") as f:
            reader=csv.reader(f,strict=True)
            for key,start,end in plan:
                part=build_shard(root,key,start,end,reader,index,global_counts)
                results.append(part);shapes.update(part["summary"]["source_coordinate_shapes"]);values.update(part["summary"]["source_value_states"])
            require(next(reader,None) is None,"source rows beyond approved partition plan")
        require(dict(shapes)==num["coordinate_shapes"] and dict(values)==num["value_states"],"whole-member structural audit mismatch")
        require(len(global_counts)==num["reports_with_cells"] and all(global_counts[k]==v[1] for k,v in index.items()),"whole-member per-report numeric count mismatch")
        require(sum(global_counts.values())==total,"whole-member parent reconciliation")
        require(sum(p["summary"]["input_numeric_rows"] for p in results)==total,"whole-member range reconciliation")
        for p in results:
            p["summary"].update({"whole_member_rows":total,"whole_member_coordinate_shapes":dict(shapes),"whole_member_value_states":dict(values),"whole_member_reconciled":True,"source_numeric_crc32":num["zip_crc32"]})
    return results

def main():
    p=argparse.ArgumentParser();p.add_argument("--source",choices=storage.LARGE_NUMERIC_ROWS,required=True);p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ)
    form=args.source;plan=scope_plan(form);parent=f"hcris-{form}-2024-index"
    ledger=json.loads(inventory.LEDGER.read_text());pins=[v for v in ledger["receipts"] if v["key"]==parent and v["kind"]=="publisher"]
    require(len(pins)==1,"exact parent index pin");pin=pins[0]
    store=storage.SourceAzure(os.environ)
    try:
        national=storage.national_manifest(store);rec=storage.existing(store,parent,pin["source_sha256"]);require(rec is not None,"parent absent")
        inventory.source_matches(rec,pin,national);prior=rec["summary"];publisher=rec["publisher"]
        require(prior["child_tables"]["numeric"]["rows"]==storage.LARGE_NUMERIC_ROWS[form],"approved whole-member count")
        db_pin=next(f for f in pin["files"] if f["path"]=="projection.sqlite3")
        existing={key:storage.existing(store,key,pin["source_sha256"]) for key,_,_ in plan}
        results=[]
        if not all(existing.values()):
            with tempfile.TemporaryDirectory(prefix="hcris-large-numeric-") as d:
                root=Path(d);source=root/"source.zip";index_db=root/"index.sqlite3"
                observed=forms.discover(form);require(observed["url"]==publisher["url"],"publisher link drift")
                meta=forms.download(observed,source)
                require(meta["sha256"]==pin["source_sha256"] and meta["bytes"]==publisher["bytes"] and sha(source)==pin["source_sha256"] and forms.discover(form)==observed,"publisher bytes/link drift")
                ext.fetch_verified(store,rec["payload_prefix"]+"/projection.sqlite3",db_pin,index_db)
                projected=project(source,index_db,prior,plan,root)
                require(sha(source)==pin["source_sha256"] and sha(index_db)==db_pin["sha256"],"source/index mutated")
                for part in projected:
                    key=part["key"];path=part["path"];summary=part["summary"]
                    summary.update({"source_index_key":parent,"source_index_sha256":db_pin["sha256"],"source_index_publisher_sha256":pin["source_sha256"]})
                    pub={**meta,"kind":"supplemental_numeric_projection","source_index_key":parent,"selected_years":["2024"],"ordinal_start":summary["ordinal_start"],"ordinal_end":summary["ordinal_end"]}
                    if existing[key] is not None:
                        old=existing[key];require(old["summary"]==summary and next(f["sha256"] for f in old["files"] if f["path"]=="projection.sqlite3")==sha(path),"existing shard differs from full replay")
                        result=old
                    else:
                        audit={"publisher":pub,"summary":summary,"projection_sha256":sha(path),"projection_bytes":path.stat().st_size,"reuse_review":"pending","public_promotion":False}
                        result=storage.publish(store,key,pub,path,audit,path.parent,national)
                    results.append(result)
                    print("PRIVATE_HCRIS_LARGE_NUMERIC_SHARD_COMPLETE",form,json.dumps(result,sort_keys=True),flush=True)
        else:results=[existing[k] for k,_,_ in plan]
        require(len(results)==len(plan),"full shard receipt coverage")
        for result,(key,start,end) in zip(results,plan):
            s=result["summary"]
            require(result["key"]==key and result["source_sha256"]==pin["source_sha256"] and result["sha256_readback"] is True and result["public_promotion"] is False and s["source_index_key"]==parent and s["source_index_sha256"]==db_pin["sha256"] and s["source_index_publisher_sha256"]==pin["source_sha256"] and s["ordinal_start"]==start and s["ordinal_end"]==end and s["whole_member_reconciled"] is True and s["input_numeric_rows"]==end-start+1 and s["stored_rows"]+s["unresolved_parent_rows"]+s["coordinate_review_rows"]+s["numeric_syntax_review_rows"]==s["input_numeric_rows"],"shard receipt lineage")
        ext.unchanged(store,national)
        summary={"status":"COMPLETE","form":form,"source_sha256":pin["source_sha256"],"source_index_key":parent,"source_index_sha256":db_pin["sha256"],"source_numeric_rows":storage.LARGE_NUMERIC_ROWS[form],"retained_numeric_rows":sum(r["summary"]["stored_rows"] for r in results),"coordinate_review_rows":sum(r["summary"]["coordinate_review_rows"] for r in results),"unresolved_parent_rows":sum(r["summary"]["unresolved_parent_rows"] for r in results),"numeric_syntax_review_rows":sum(r["summary"]["numeric_syntax_review_rows"] for r in results),"shards":len(results),"payload_bytes":sum(r["total_bytes"] for r in results),"public_promotion":False,"all_shard_sha256_readback":True,"receipts":results}
        require(summary["source_numeric_rows"]==sum(summary[k] for k in ("retained_numeric_rows","coordinate_review_rows","unresolved_parent_rows","numeric_syntax_review_rows")),"final form accounting")
        with args.receipt.open("xb") as f:f.write(a.encode(summary))
        print("PRIVATE_HCRIS_LARGE_NUMERIC_COMPLETE",form,json.dumps({k:v for k,v in summary.items() if k!="receipts"},sort_keys=True),flush=True)
        # Always emit receipts, including a fully recovered prior run.
        for result in results:print("PRIVATE_HCRIS_LARGE_NUMERIC_RECEIPT",form,json.dumps(result,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
