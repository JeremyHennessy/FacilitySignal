"""Private exact institutional NPI candidates, not a canonical master merge."""
import argparse,hashlib,json,os,re,sqlite3,tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path
import azure_national_archive as a
from scripts import azure_source_archive as storage,azure_verified_extension as ext,qualify_nppes_v2 as nppes
from build_combined import require,readonly,sha,check_integrity
NPPES_PIN="c5a34fba9b2e04bcb87358a1e3f9f4bbfc79b49b71fb37b71f9de43570c18713"
NPPES_DB_PIN="5a96956900039839bcf31017cf54d4f4e4f4388128281e6c98ba0d7e072d7bf7"
FAMILIES={"hospital-enrollment":("hospital","rehabilitation","long-term-hospital"),"snf-enrollment":("nursing",)}
def projection(base,registry,out,expected=None):
    with closing(readonly(base)) as src,closing(readonly(registry)) as reg,closing(sqlite3.connect(out)) as db:
        check_integrity(src);check_integrity(reg)
        db.execute("CREATE TABLE candidates(source TEXT NOT NULL,source_ordinal INTEGER NOT NULL,enrollment_id TEXT NOT NULL,ccn TEXT,npi TEXT NOT NULL,registry_region_state TEXT NOT NULL,care_compare_candidate_state TEXT NOT NULL,PRIMARY KEY(source,source_ordinal)) WITHOUT ROWID")
        counts={};total=0
        for family,datasets in FAMILIES.items():
            c=Counter();where=",".join("?" for _ in datasets)
            for ordinal,enrollment,ccn,npi,state in src.execute("SELECT ordinal,enrollment_id,ccn,npi,upper(trim(json_extract(projection,'$.STATE'))) FROM pecos_enrollment_rows WHERE source=?",(family,)):
                total+=1;c["input_rows"]+=1
                npi=(npi or "").strip()
                if not npi_valid(npi):c["missing_or_invalid_npi"]+=1;continue
                hit=reg.execute("SELECT practice_state FROM organization_fields WHERE npi=?",(npi,)).fetchone()
                if hit is None:c["not_in_qualified_type2_release"]+=1;continue
                c["type2_exact_npi"]+=1
                state=(state or "").strip().upper()
                state_ok=re.fullmatch(r"[A-Z]{2}",state) is not None
                rg=hit[0]
                region="unavailable" if not state_ok or not rg else "same" if state==rg else "different"
                cc=(ccn or "").strip()
                if not re.fullmatch(r"[A-Z0-9]{6}",cc):cc=None
                if cc is None:care="missing_or_invalid_ccn"
                else:
                    hits={x[0] for x in src.execute("SELECT state FROM facilities WHERE ccn=? AND dataset IN ("+where+")",(cc,*datasets))}
                    care="no_ccn_candidate" if not hits else "same_state_ccn" if state_ok and state in hits else "ccn_without_state_agreement"
                db.execute("INSERT INTO candidates VALUES(?,?,?,?,?,?,?)",(family,ordinal,enrollment,cc,npi,region,care))
                c["nppes_region_"+region]+=1;c["care_compare_"+care]+=1
            require(c["input_rows"]==c["type2_exact_npi"]+c["missing_or_invalid_npi"]+c["not_in_qualified_type2_release"],"NPI reconciliation")
            require(c["type2_exact_npi"]==sum(v for k,v in c.items() if k.startswith("nppes_region_"))==sum(v for k,v in c.items() if k.startswith("care_compare_")),"candidate states")
            counts[family]=dict(c)
        if expected is not None:require(total==expected,"enrollment count changed")
        db.execute("CREATE INDEX candidates_npi ON candidates(npi)")
        db.execute("CREATE INDEX candidates_ccn ON candidates(ccn)")
        db.commit();check_integrity(db)
        stored=db.execute("SELECT count(*) FROM candidates").fetchone()[0]
        require(stored==sum(x.get("type2_exact_npi",0) for x in counts.values()),"stored candidate count")
        summary={"input_enrollment_rows":total,"stored_candidate_rows":stored,"by_source":counts,"distinct_type2_npis":db.execute("SELECT count(DISTINCT npi) FROM candidates").fetchone()[0],"distinct_ccns_with_candidates":db.execute("SELECT count(DISTINCT ccn) FROM candidates").fetchone()[0],"npis_with_multiple_enrollment_candidates":db.execute("SELECT count(*) FROM (SELECT npi FROM candidates GROUP BY npi HAVING count(*)>1)").fetchone()[0],"individual_or_unmatched_npi_values_retained":0,"scope":"Exact NPI membership in November 2026 Type 2 release, independent CCN/state evidence. No current active status, site or ownership merge."}
    return summary
def npi_valid(v):return nppes.npi_valid(v)
def main():
    p=argparse.ArgumentParser();p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ);store=storage.SourceAzure(os.environ)
    try:
        national=storage.national_manifest(store)
        prefix=storage.prefix_for("nppes-monthly",NPPES_PIN)
        rec,_,_=ext.read_small(store,prefix+"/complete.json")
        require(rec["domain"]=="FACILITYSIGNAL_PRIVATE_SOURCE" and rec["status"]=="COMPLETE" and rec["source_sha256"]==NPPES_PIN and rec["key"]=="nppes-monthly" and rec["base_receipt_sha256"]==national["receipt_sha256"] and rec["summary"]["organization_observations"]==1990237,"NPPES archive receipt")
        pin=next(x for x in rec["files"] if x["path"]=="projection.sqlite3")
        require(pin["sha256"]==NPPES_DB_PIN and 0<pin["bytes"]<=storage.MAX_DB,"monthly DB pin")
        # Derived release identity depends on both verified input database hashes.
        inputs={"national_database_sha256":national["receipt"]["database_sha256"],"nppes_database_sha256":pin["sha256"],"policy_version":1}
        identity=hashlib.sha256(a.encode(inputs)).hexdigest()
        receipt=storage.existing(store,"pecos-nppes-identity-candidates",identity)
        if receipt is None:
            with tempfile.TemporaryDirectory(prefix="npi-linkage-") as d:
                root=Path(d);base,_=ext.restore_national(store,national,root/"base")
                registry=root/"nppes.sqlite3";ext.fetch_verified(store,prefix+"/files/projection.sqlite3",pin,registry)
                with closing(readonly(registry)) as conn:
                    require(conn.execute("SELECT count(*) FROM organization_fields").fetchone()[0]==1990237,"monthly organization count")
                out=root/"projection.sqlite3";summary=projection(base,registry,out,23521)
                require(sha(base)==inputs["national_database_sha256"] and sha(registry)==inputs["nppes_database_sha256"],"input database changed")
                meta={"sha256":identity,"kind":"derived_identity_candidate_release","inputs":inputs}
                audit={"input_archives":inputs,"summary":summary,"projection_sha256":sha(out),"projection_bytes":out.stat().st_size,"reuse_review":"pending","public_promotion":False}
                receipt=storage.publish(store,"pecos-nppes-identity-candidates",meta,out,audit,root,national)
        args.receipt.write_bytes(a.encode(receipt))
        print("PRIVATE_PECOS_NPPES_CANDIDATES_COMPLETE",json.dumps(receipt,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
