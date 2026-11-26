"""Archive exact numeric child observations against completed HCRIS report indexes.

Use the exact publisher archive bytes, original annual report scope and ordinal.
Retain bounded coordinates and decimal source text, not interpreted measures or
alpha values. Review exceptions are counted and not attached to a guessed report.
The new payload is supplemental to the existing publisher release, not another
publisher release or another set of report observations.
"""
import argparse,csv,io,json,os,re,sqlite3,tempfile,zipfile
from collections import Counter
from contextlib import closing
from pathlib import Path
import azure_national_archive as a
from build_combined import require,sha,readonly,check_integrity
from scripts import archive_hcris_form_indexes as forms,qualify_hcris_hha as h
from scripts import azure_source_archive as storage,audit_azure_archive_inventory as inventory,azure_verified_extension as ext
SCOPES={
 "cmhc":("hcris-cmhc-2017-numeric",None),
 "rhc":("hcris-rhc-2017-numeric",None),
 "fqhc":("hcris-fqhc-2024-numeric",("2024",)),
 "hospice":("hcris-hospice-2024-numeric",("2024",)),
 "renal":("hcris-renal-2024-numeric",("2024",)),
}
MAX_CELLS=4_000_000
MAX_DB=350_000_000
BATCH=10000

def project(path,index_db,out,prior,years):
    require(not out.exists(),"new numeric projection required")
    with zipfile.ZipFile(path) as z,closing(readonly(index_db)) as idx,closing(sqlite3.connect(out)) as db:
        check_integrity(idx)
        groups=forms.annual_groups(z)
        expected=prior["annual_partitions"]
        require(set(groups)==set(expected),"annual index inventory differs")
        chosen=sorted(groups) if years is None else list(years)
        require(chosen and len(chosen)==len(set(chosen)) and set(chosen)<=set(groups),"invalid partition selection")
        require(sum(expected[y]["child_tables"]["numeric"]["rows"] for y in chosen)<=MAX_CELLS,"numeric partition source-row budget")
        require(idx.execute("SELECT count(*) FROM reports").fetchone()[0]==prior["stored_rows"],"prior report index count")
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
        CREATE TABLE report_references(source_year TEXT NOT NULL,report_key TEXT NOT NULL,PRIMARY KEY(source_year,report_key)) WITHOUT ROWID;
        CREATE TABLE numeric_cells(source_year TEXT NOT NULL,ordinal INTEGER NOT NULL,report_key TEXT NOT NULL,worksheet TEXT NOT NULL,line TEXT NOT NULL,col TEXT NOT NULL,value_text TEXT NOT NULL,value_state TEXT NOT NULL,PRIMARY KEY(source_year,ordinal),FOREIGN KEY(source_year,report_key) REFERENCES report_references(source_year,report_key)) WITHOUT ROWID;
        """)
        totals=Counter();details={}
        for year in chosen:
            roles=groups[year];pin=expected[year];num=pin["child_tables"]["numeric"]
            require(roles["numeric"].file_size==num["uncompressed_bytes"] and format(roles["numeric"].CRC,"08x")==num["zip_crc32"],"numeric ZIP member identity")
            index_rows={key:(ordinal,numeric,alpha) for key,ordinal,numeric,alpha in idx.execute("SELECT report_key,ordinal,numeric_rows,alpha_rows FROM reports WHERE source_year=?",(year,))}
            require(len(index_rows)==pin["report_rows"],"annual parent count")
            seen=set();widths=Counter()
            with z.open(roles["report"]) as raw,io.TextIOWrapper(raw,encoding="latin-1",newline="") as f:
                for ordinal,row in enumerate(csv.reader(f,strict=True),1):
                    require(ordinal<=150000 and 2<=len(row)<=100,"report row shape")
                    key=h.report_key(row[0]);require(key in index_rows and key not in seen and index_rows[key][0]==ordinal,"report key or ordinal drift")
                    seen.add(key);widths[str(len(row))]+=1
            require(seen==set(index_rows) and dict(widths)==pin["report_width_counts"],"report source/index mismatch")
            db.executemany("INSERT INTO report_references VALUES(?,?)",((year,k) for k in sorted(seen)))
            shapes=Counter();values=Counter();link=Counter();matched=Counter();retained=Counter();dispositions=Counter();batch=[];n=0
            with z.open(roles["numeric"]) as raw,io.TextIOWrapper(raw,encoding="latin-1",newline="") as f:
                for n,row in enumerate(csv.reader(f,strict=True),1):
                    require(n<=num["rows"] and len(row)==5,"numeric child width or bound")
                    key=h.report_key(row[0]);w,l,c=(v.strip() for v in row[1:4]);value=row[4].strip()
                    bounded=bool(re.fullmatch(r"[A-Z0-9*]{1,7}",w) and re.fullmatch(r"[0-9A-Z]{1,5}",l) and re.fullmatch(r"[0-9A-Z]{1,5}",c))
                    state=h.cell_state(value)
                    shapes["bounded_source_coordinate" if bounded else "coordinate_review"]+=1;values[state]+=1
                    if key not in index_rows:
                        link["invalid_parent_key" if key is None else "unmatched_parent_key"]+=1;dispositions["unresolved_parent"]+=1;continue
                    link["matched_parent"]+=1;matched[key]+=1
                    if not bounded:dispositions["coordinate_review"]+=1;continue
                    if state=="unrecognized":dispositions["numeric_syntax_review"]+=1;continue
                    dispositions["retained"]+=1;retained[state]+=1
                    batch.append((year,n,key,w,l,c,value,state))
                    if len(batch)>=BATCH:
                        db.executemany("INSERT INTO numeric_cells VALUES(?,?,?,?,?,?,?,?)",batch);batch.clear()
                        require(db.execute("PRAGMA page_count").fetchone()[0]*db.execute("PRAGMA page_size").fetchone()[0]<=MAX_DB,"numeric projection storage budget")
                if batch:db.executemany("INSERT INTO numeric_cells VALUES(?,?,?,?,?,?,?,?)",batch)
            require(n==num["rows"]==sum(shapes.values())==sum(values.values())==sum(link.values())==sum(dispositions.values()),"numeric source accounting")
            require(dict(shapes)==num["coordinate_shapes"] and dict(values)==num["value_states"],"prior numeric structural audit mismatch")
            require(len(matched)==num["reports_with_cells"] and all(matched[k]==v[1] for k,v in index_rows.items()),"per-report matched child count mismatch")
            if "parent_linkage" in num:require(dict(link)==num["parent_linkage"],"prior unresolved-parent count mismatch")
            else:require(link.get("matched_parent",0)==n,"earlier index required clean parent linkage")
            actual=dict(db.execute("SELECT value_state,count(*) FROM numeric_cells WHERE source_year=? GROUP BY value_state",(year,)))
            require(actual==dict(retained) and sum(retained.values())==dispositions["retained"],"numeric retained state reconciliation")
            details[year]={"input_numeric_rows":n,"report_references":len(seen),"parent_linkage":dict(link),"source_coordinate_shapes":dict(shapes),"source_value_states":dict(values),"retained_value_states":dict(retained),"dispositions":dict(dispositions),"source_numeric_crc32":num["zip_crc32"]}
            totals.update(dispositions);totals["input_numeric_rows"]+=n
        db.execute("CREATE INDEX numeric_report_lookup ON numeric_cells(source_year,report_key)")
        db.commit();check_integrity(db)
        require(0<out.stat().st_size<=MAX_DB,"numeric projection final size")
        stored=db.execute("SELECT count(*) FROM numeric_cells").fetchone()[0]
        require(stored==totals["retained"]>0 and totals["input_numeric_rows"]==sum(totals[k] for k in ("retained","unresolved_parent","coordinate_review","numeric_syntax_review")),"numeric total reconciliation")
        repeated=db.execute("SELECT coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM numeric_cells GROUP BY source_year,report_key,worksheet,line,col HAVING n>1)").fetchone()[0]
        return {"stored_rows":stored,"supplemental_numeric_rows":stored,"input_numeric_rows":totals["input_numeric_rows"],"unresolved_parent_rows":totals["unresolved_parent"],"coordinate_review_rows":totals["coordinate_review"],"numeric_syntax_review_rows":totals["numeric_syntax_review"],"repeated_coordinate_rows":repeated,"annual_partitions":details,"report_references_not_counted":db.execute("SELECT count(*) FROM report_references").fetchone()[0],"alpha_values_retained":0,"new_publisher_release":False,"units_interpreted":False,"public_promotion":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--source",choices=SCOPES,required=True);p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ)
    key,years=SCOPES[args.source];parent=storage.SUPPLEMENTAL_NUMERIC_PARENTS[key]
    ledger=json.loads(inventory.LEDGER.read_text());pins=[v for v in ledger["receipts"] if v["key"]==parent and v["kind"]=="publisher"]
    require(len(pins)==1,"exact report index pin required");pin=pins[0]
    store=storage.SourceAzure(os.environ)
    try:
        national=storage.national_manifest(store)
        parent_rec=storage.existing(store,parent,pin["source_sha256"]);require(parent_rec is not None,"parent receipt absent")
        inventory.source_matches(parent_rec,pin,national)
        prior=parent_rec["summary"];publisher=parent_rec["publisher"]
        result=storage.existing(store,key,pin["source_sha256"])
        if result is None:
            with tempfile.TemporaryDirectory(prefix="hcris-numeric-partition-") as d:
                root=Path(d);source=root/"source.zip";index_db=root/"index.sqlite3";out=root/"projection.sqlite3"
                observed=forms.discover(args.source);require(observed["url"]==publisher["url"],"publisher link drift")
                meta=forms.download(observed,source)
                require(meta["sha256"]==pin["source_sha256"] and meta["bytes"]==publisher["bytes"] and sha(source)==pin["source_sha256"],"publisher bytes differ from index")
                require(forms.discover(args.source)==observed,"publisher link changed during retrieval")
                db_pin=next(f for f in pin["files"] if f["path"]=="projection.sqlite3")
                ext.fetch_verified(store,parent_rec["payload_prefix"]+"/projection.sqlite3",db_pin,index_db)
                summary=project(source,index_db,out,prior,years)
                require(sha(source)==pin["source_sha256"] and sha(index_db)==db_pin["sha256"],"source/index mutated")
                summary.update({"source_index_key":parent,"source_index_sha256":db_pin["sha256"],"source_index_publisher_sha256":pin["source_sha256"]})
                source.unlink();index_db.unlink()
                pub={**meta,"kind":"supplemental_numeric_projection","source_index_key":parent,"selected_years":sorted(summary["annual_partitions"])}
                audit={"publisher":pub,"summary":summary,"projection_sha256":sha(out),"projection_bytes":out.stat().st_size,"reuse_review":"pending","public_promotion":False}
                result=storage.publish(store,key,pub,out,audit,root,national)
        require(result["summary"]["source_index_key"]==parent and result["summary"]["source_index_publisher_sha256"]==pin["source_sha256"] and result["summary"]["source_index_sha256"]==next(f["sha256"] for f in pin["files"] if f["path"]=="projection.sqlite3") and (years is None or sorted(result["summary"]["annual_partitions"])==sorted(years)),"supplemental receipt lineage")
        with args.receipt.open("xb") as f:f.write(a.encode(result))
        print("PRIVATE_HCRIS_NUMERIC_COMPLETE",args.source,json.dumps(result,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
