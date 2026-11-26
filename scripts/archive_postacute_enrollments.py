"""Archive current CMS postacute enrollments with institutional NPI corroboration.

No individual or unmatched identifiers, names, addresses, raw files or public
pack changes. Exact enrollment/PAC and CCN/state links are evidence only.
"""
import argparse,csv,json,os,re,sqlite3,tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path
import azure_national_archive as a
import collect_registry as registry
from probe_ownership import select
from scripts import azure_source_archive as storage,azure_verified_extension as ext
from scripts import archive_postacute_sources as post,archive_pecos_nppes_candidates as identity
from build_combined import require,readonly,sha,check_integrity
ROOT=Path(__file__).resolve().parents[1]
PERIOD="2026-10-01/2026-12-31"
TARGETS={
 "hha":{"title":"Home Health Agency Enrollments","code":"00-06","key":"hha-enrollment-organizations","directory":"home-health","owner_key":"hha-organizational-ownership","owner_sha":"75f6de0bde699b85de15f8b206b3c287afc05388400b78e7ee42284f15ebbf02","owner_db_sha":"c24ef49cb070c8e4adce595d68aecee02d060c97e9348fd969c0bac8ba230681","owner_rows":21734},
 "hospice":{"title":"Hospice Enrollments","code":"00-08","key":"hospice-enrollment-organizations","directory":"hospice","owner_key":"hospice-organizational-ownership","owner_sha":"23de741ded45d49bb889fb2df3d8330d0884bf241c876d42cd47d93cf1ba208f","owner_db_sha":"440fb9e042220f35712c0386a0302cb049dc2eb19e725539e4d024b73d7c8e1f","owner_rows":18763}}
FIELDS={"ENROLLMENT ID","ASSOCIATE ID","CCN","NPI","PROVIDER TYPE CODE","STATE","ENROLLMENT STATE"}

def selection(catalog,t):
    m=select(catalog,t["title"])
    require(m["period"]==PERIOD and re.fullmatch(r"https://data\.cms\.gov/data-api/v1/dataset/[0-9a-f-]{36}/data",m["api"]),"unexpected enrollment publisher quarter/version")
    require(len(m["distributions"])==1 and m["distributions"][0]["format"]=="CSV","CSV distribution scope")
    return {**m,"url":m["distributions"][0]["url"],"zipped":False}

def restore_input(store,national,key,source_sha,db_sha,path):
    prefix=storage.prefix_for(key,source_sha)
    rec,_,_=ext.read_small(store,prefix+"/complete.json")
    require(rec["status"]=="COMPLETE" and rec["domain"]=="FACILITYSIGNAL_PRIVATE_SOURCE" and rec["key"]==key and rec["source_sha256"]==source_sha and rec["base_receipt_sha256"]==national["receipt_sha256"] and rec["sha256_readback"] is True,"input archive receipt")
    pin=next(x for x in rec["files"] if x["path"]=="projection.sqlite3")
    require(pin["sha256"]==db_sha and 0<pin["bytes"]<=storage.MAX_DB,"input database pin")
    ext.fetch_verified(store,prefix+"/files/projection.sqlite3",pin,path)
    with closing(readonly(path)) as db:check_integrity(db)
    return rec

def project(path,api_fields,n,t,registry_path,owner_path,providers,out):
    enc=registry.source_encoding(path,False)
    counts=Counter();seen=set()
    with closing(readonly(registry_path)) as reg,closing(readonly(owner_path)) as owners,closing(sqlite3.connect(out)) as db:
        require(owners.execute("SELECT count(*) FROM pecos_org_role_rows").fetchone()[0]==t["owner_rows"],"owner source count")
        db.execute("CREATE TABLE enrollment_observations(ordinal INTEGER PRIMARY KEY,enrollment_id TEXT NOT NULL UNIQUE,pac_id TEXT NOT NULL,npi TEXT NOT NULL,ccn TEXT,practice_state TEXT,enrollment_state TEXT,owner_candidate_state TEXT NOT NULL,care_compare_candidate_state TEXT NOT NULL,nppes_region_state TEXT NOT NULL)")
        with registry.open_csv(path,False,enc) as f:
            reader=csv.DictReader(f);header=reader.fieldnames or []
            require(len(header)==len(set(header))==len(api_fields) and set(header)==set(api_fields) and FIELDS<=set(header),"CSV/API schema")
            for ordinal,row in enumerate(reader,2):
                counts["input_rows"]+=1
                require(None not in row and all(v is not None for v in row.values()),"malformed CSV row")
                require(row["PROVIDER TYPE CODE"].strip()==t["code"],"unexpected enrollment specialty")
                e=row["ENROLLMENT ID"].strip();p=row["ASSOCIATE ID"].strip()
                require(re.fullmatch(r"[A-Za-z0-9]{15}",e) and re.fullmatch(r"[0-9]{1,10}",p) and e not in seen,"enrollment/PAC identifier or duplicate")
                seen.add(e)
                npi=row["NPI"].strip()
                if not identity.npi_valid(npi):
                    counts["missing_or_invalid_npi"]+=1;continue
                hit=reg.execute("SELECT practice_state FROM organization_fields WHERE npi=?",(npi,)).fetchone()
                if hit is None:
                    counts["not_in_type2_reference"]+=1;continue
                def state(v):
                    v=v.strip().upper()
                    return v if re.fullmatch(r"[A-Z]{2}",v) else None
                practice=state(row["STATE"]);enrolled=state(row["ENROLLMENT STATE"])
                cc=row["CCN"].strip()
                cc=cc if re.fullmatch(r"[A-Z0-9]{6}",cc) else None
                region="unavailable" if not practice or not hit[0] else "same" if practice==hit[0] else "different"
                owner="exact_enrollment_pac" if owners.execute("SELECT 1 FROM pecos_org_role_rows WHERE enrollment_id=? AND pac_id=? LIMIT 1",(e,p)).fetchone() else "no_exact_owner_candidate"
                states=providers.get(cc,set())
                care="missing_or_invalid_ccn" if cc is None else "no_ccn_candidate" if not states else "same_practice_state_ccn" if practice in states else "ccn_without_practice_state_agreement"
                db.execute("INSERT INTO enrollment_observations VALUES(?,?,?,?,?,?,?,?,?,?)",(ordinal,e,p,npi,cc,practice,enrolled,owner,care,region))
                counts["stored_rows"]+=1
                counts["owner_"+owner]+=1;counts["care_compare_"+care]+=1;counts["nppes_region_"+region]+=1
        require(counts["input_rows"]==n==counts["stored_rows"]+counts["missing_or_invalid_npi"]+counts["not_in_type2_reference"] and counts["stored_rows"]>0,"enrollment row reconciliation")
        for domain in ("owner_","care_compare_","nppes_region_"):
            require(sum(v for k,v in counts.items() if k.startswith(domain))==counts["stored_rows"],"candidate domain reconciliation")
        db.execute("CREATE INDEX enrollment_npi ON enrollment_observations(npi)")
        db.execute("CREATE INDEX enrollment_ccn ON enrollment_observations(ccn)")
        db.commit();check_integrity(db)
        require(db.execute("SELECT count(*) FROM enrollment_observations").fetchone()[0]==counts["stored_rows"],"stored count")
        return {**dict(counts),"source_columns":len(api_fields),"individual_or_unmatched_identifiers_retained":0,"names_addresses_contacts_retained":0,"public_promotion":False,"scope":"CMS enrollment observations whose NPI has exact Type 2 membership in the pinned November NPPES release. Role and CCN/state matches are candidates, not a current site or ownership merge."}

def main():
    p=argparse.ArgumentParser();p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ)
    store=storage.SourceAzure(os.environ);receipts=[]
    try:
        national=storage.national_manifest(store)
        with tempfile.TemporaryDirectory(prefix="postacute-enrollment-") as d:
            root=Path(d);reg=root/"nppes.sqlite3"
            rec=restore_input(store,national,"nppes-monthly",identity.NPPES_PIN,identity.NPPES_DB_PIN,reg)
            require(rec["summary"]["organization_observations"]==1990237,"NPPES count")
            with closing(readonly(reg)) as db:require(db.execute("SELECT count(*) FROM organization_fields").fetchone()[0]==1990237,"NPPES database count")
            for family,t in TARGETS.items():
                meta=selection(registry.get_json(registry.CATALOG),t);n=registry.expected_rows(meta)
                require(0<n<=50000,"enrollment count bound")
                sample=registry.get_json(meta["api"]+"?size=1")
                require(isinstance(sample,list) and len(sample)==1 and isinstance(sample[0],dict),"API schema sample")
                fields=list(sample[0]);require(FIELDS<=set(fields) and 0<len(fields)<=200,"required enrollment fields")
                work=root/family;work.mkdir();source=work/"source.csv"
                digest,size=post.fetch(meta,source,80_000_000)
                require(selection(registry.get_json(registry.CATALOG),t)==meta and registry.expected_rows(meta)==n,"publisher metadata drift")
                publisher={**meta,"sha256":digest,"bytes":size}
                receipt=storage.existing(store,t["key"],digest)
                if receipt is None:
                    owner=work/"owners.sqlite3"
                    owner_receipt=restore_input(store,national,t["owner_key"],t["owner_sha"],t["owner_db_sha"],owner)
                    require(owner_receipt["summary"]["organization_role_rows"]==t["owner_rows"] and owner_receipt["publisher"]["period"]==PERIOD,"ownership quarter/count mismatch")
                    pack="web/public-directory/"+t["directory"]+".json";local=ROOT/pack;pin=national["files"][pack]
                    require(sha(local)==pin["sha256"],"directory pack drift")
                    a.verify(store,national["receipt"]["payload_prefix"]+"/"+pack,pin)
                    providers={}
                    for row in json.loads(local.read_text())["records"]:providers.setdefault(row["ccn"],set()).add(row["state"])
                    db=work/"projection.sqlite3";summary=project(source,fields,n,t,reg,owner,providers,db)
                    require(sha(source)==digest and sha(reg)==identity.NPPES_DB_PIN and sha(owner)==t["owner_db_sha"],"input changed")
                    source.unlink()
                    summary["reference_db_sha256"]={"nppes":identity.NPPES_DB_PIN,"owner":t["owner_db_sha"],"care_compare_pack":pin["sha256"]}
                    audit={"publisher":publisher,"summary":summary,"projection_sha256":sha(db),"projection_bytes":db.stat().st_size,"reuse_review":"pending","public_promotion":False}
                    receipt=storage.publish(store,t["key"],publisher,db,audit,work,national)
                receipts.append(receipt);print("PRIVATE_POSTACUTE_ENROLLMENT_COMPLETE",family,json.dumps(receipt,sort_keys=True),flush=True)
        with args.receipt.open("xb") as f:f.write(a.encode(receipts))
    finally:store.close()
if __name__=="__main__":main()
