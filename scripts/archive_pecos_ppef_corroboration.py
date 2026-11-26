"""Private enrollment corroboration from already verified Azure archives.

Compare source-scoped enrollment ID, PAC, institutional NPI and provider type.
Store source row references and evidence states only, not names or raw identifiers.
No canonical merges, source downloads, public data or pointer changes.
"""
import argparse,hashlib,json,os,re,sqlite3,tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path
import azure_national_archive as a
from build_combined import require,readonly,sha,check_integrity
from scripts import azure_source_archive as storage,azure_verified_extension as ext
from scripts import audit_azure_archive_inventory as audit,archive_pecos_nppes_candidates as identity

ROOT=Path(__file__).resolve().parents[1]
KEY="pecos-ppef-enrollment-corroboration"
KIND="derived_enrollment_corroboration"
FAMILIES={"hospital-enrollment":("hospital-owner",{"00-09","00-24","00-85"}),"snf-enrollment":("snf-owner",{"00-18"}),"hha-enrollment-organizations":(None,{"00-06"}),"hospice-enrollment-organizations":(None,{"00-08"})}
INPUT_KEYS=("pecos-nppes-identity-candidates","hha-enrollment-organizations","hospice-enrollment-organizations","ppef-type2-enrollment")
EXPECTED_INPUT={"pecos-nppes-identity-candidates":23520,"hha-enrollment-organizations":11505,"hospice-enrollment-organizations":5684,"ppef-type2-enrollment":380892}
EXPECTED_TOTAL=40709
DDL="""CREATE TABLE enrollment_corroboration(
 source_family TEXT NOT NULL, source_ordinal INTEGER NOT NULL,
 ppef_candidate_ordinal INTEGER, disposition TEXT NOT NULL
 CHECK(disposition IN ('exact_all_keys','exact_enrollment_id_conflict','no_exact_enrollment_id','key_shape_review')),
 pac_agrees INTEGER CHECK(pac_agrees IN (0,1)),
 npi_agrees INTEGER CHECK(npi_agrees IN (0,1)),
 provider_type_agrees INTEGER CHECK(provider_type_agrees IN (0,1)),
 alternative_key_candidates INTEGER CHECK(alternative_key_candidates>=0),
 care_compare_state TEXT NOT NULL, nppes_region_state TEXT NOT NULL, owner_candidate_state TEXT NOT NULL,
 PRIMARY KEY(source_family,source_ordinal)) WITHOUT ROWID;
 CREATE INDEX enrollment_corroboration_filter ON enrollment_corroboration(source_family,disposition,care_compare_state);
 CREATE INDEX enrollment_corroboration_ppef ON enrollment_corroboration(ppef_candidate_ordinal);
 """
def scalar(db,sql,args=()):return db.execute(sql,args).fetchone()[0]
def key_shape(e,p,n,c):
    return isinstance(e,str) and re.fullmatch(r"[A-Za-z0-9]{15}",e) is not None and isinstance(p,str) and re.fullmatch(r"[0-9]{1,10}",p) is not None and isinstance(n,str) and identity.npi_valid(n) and isinstance(c,str) and re.fullmatch(r"[0-9]{2}-[0-9]{2}",c) is not None
def compare(db,e,p,n,c):
    if not key_shape(e,p,n,c):return (None,"key_shape_review",None,None,None,None)
    hit=db.execute("SELECT ordinal,pac_id,npi,provider_type_code FROM enrollment_observations WHERE enrollment_id=?",(e,)).fetchone()
    if hit is None:
        count=scalar(db,"SELECT count(*) FROM enrollment_observations WHERE pac_id=? AND npi=? AND provider_type_code=?",(p,n,c))
        return (None,"no_exact_enrollment_id",None,None,None,count)
    ordinal,pac,npi,code=hit
    flags=(int(p==pac),int(n==npi),int(c==code))
    return (ordinal,"exact_all_keys" if all(flags) else "exact_enrollment_id_conflict",*flags,None)

def national_rows(base,candidates):
    for family,(owner,codes) in FAMILIES.items():
        if owner is None:continue
        for ordinal,e,n,region,care in candidates.execute("SELECT source_ordinal,enrollment_id,npi,registry_region_state,care_compare_candidate_state FROM candidates WHERE source=? ORDER BY source_ordinal",(family,)):
            record=base.execute("SELECT enrollment_id,pac_id,npi,json_extract(projection,'$.PROVIDER TYPE CODE') FROM pecos_enrollment_rows WHERE source=? AND ordinal=?",(family,ordinal)).fetchone()
            require(record is not None and record[0]==e and record[2]==n,"national candidate reference drift")
            _,p,_,c=record
            require(c in codes,"national provider type changed")
            owner_state="exact_enrollment_pac" if p and e and base.execute("SELECT 1 FROM pecos_org_role_rows WHERE source=? AND enrollment_id=? AND pac_id=? LIMIT 1",(owner,e,p)).fetchone() else "no_exact_owner_candidate"
            yield family,ordinal,e,p,n,c,care,region,owner_state
def postacute_rows(db,family):
    _,codes=FAMILIES[family];require(len(codes)==1,"postacute scope")
    code=next(iter(codes))
    for ordinal,e,p,n,care,region,owner in db.execute("SELECT ordinal,enrollment_id,pac_id,npi,care_compare_candidate_state,nppes_region_state,owner_candidate_state FROM enrollment_observations ORDER BY ordinal"):
        yield family,ordinal,e,p,n,code,care,region,owner

def projection(out,ppef,rows,expected=None):
    require(not out.exists(),"output exists")
    counts={};n=0
    with closing(sqlite3.connect(out)) as db:
        db.executescript(DDL)
        for family,ordinal,e,p,npi,code,care,region,owner in rows:
            require(family in FAMILIES and type(ordinal) is int and ordinal>=2 and code in FAMILIES[family][1],"family/ordinal/type scope")
            require(region in ("same","different","unavailable") and owner in ("exact_enrollment_pac","no_exact_owner_candidate"),"relationship state scope")
            require(care in ("missing_or_invalid_ccn","no_ccn_candidate","same_state_ccn","ccn_without_state_agreement","same_practice_state_ccn","ccn_without_practice_state_agreement"),"Care Compare state scope")
            result=compare(ppef,e,p,npi,code)
            db.execute("INSERT INTO enrollment_corroboration VALUES(?,?,?,?,?,?,?,?,?,?,?)",(family,ordinal,*result,care,region,owner))
            c=counts.setdefault(family,Counter());n+=1
            c["rows"]+=1;c[result[1]]+=1
            if result[1]=="exact_enrollment_id_conflict":
                c["conflict_pac_"+("agrees" if result[2] else "differs")]+=1
                c["conflict_npi_"+("agrees" if result[3] else "differs")]+=1
                c["conflict_type_"+("agrees" if result[4] else "differs")]+=1
            elif result[1]=="no_exact_enrollment_id":
                c["alternative_key_"+("none" if result[5]==0 else "one" if result[5]==1 else "multiple")]+=1
            if result[1]=="exact_all_keys":
                c["all_keys_care_"+care]+=1;c["all_keys_region_"+region]+=1;c["all_keys_owner_"+owner]+=1
        if expected is not None:require(n==expected and set(counts)==set(FAMILIES),"input coverage")
        db.commit();check_integrity(db)
        require(scalar(db,"SELECT count(*) FROM enrollment_corroboration")==n,"row reconciliation")
        for family,c in counts.items():
            actual=dict(db.execute("SELECT disposition,count(*) FROM enrollment_corroboration WHERE source_family=? GROUP BY disposition",(family,)))
            require(sum(actual.values())==c["rows"] and all(c[k]==v for k,v in actual.items()),"disposition reconciliation")
            for prefix,target in (("conflict_pac_",c["exact_enrollment_id_conflict"]),("conflict_npi_",c["exact_enrollment_id_conflict"]),("conflict_type_",c["exact_enrollment_id_conflict"]),("alternative_key_",c["no_exact_enrollment_id"]),("all_keys_care_",c["exact_all_keys"]),("all_keys_region_",c["exact_all_keys"]),("all_keys_owner_",c["exact_all_keys"])):
                require(sum(v for k,v in c.items() if k.startswith(prefix))==target,"subdomain reconciliation")
        all_states=dict(db.execute("SELECT disposition,count(*) FROM enrollment_corroboration GROUP BY disposition"))
        require(scalar(db,"SELECT count(*) FROM enrollment_corroboration WHERE disposition='exact_all_keys' AND (pac_agrees<>1 OR npi_agrees<>1 OR provider_type_agrees<>1 OR ppef_candidate_ordinal IS NULL)")==0,"exact-key evidence")
        require(scalar(db,"SELECT count(*) FROM enrollment_corroboration WHERE disposition IN ('no_exact_enrollment_id','key_shape_review') AND ppef_candidate_ordinal IS NOT NULL")==0,"alternative link must remain unresolved")
        require(scalar(db,"SELECT count(*) FROM enrollment_corroboration WHERE disposition='exact_all_keys' AND alternative_key_candidates IS NOT NULL")==0,"alternate/exact overlap")
        distinct_exact=scalar(db,"SELECT count(DISTINCT ppef_candidate_ordinal) FROM enrollment_corroboration WHERE disposition='exact_all_keys'")
    return {"stored_enrollment_evidence_rows":n,"dispositions":all_states,"by_family":{k:dict(v) for k,v in counts.items()},"distinct_ppef_ordinals_with_all_key_agreement":distinct_exact,"new_publisher_release":False,"publisher_downloads":0,"canonical_merges":0,"raw_identifiers_in_projection":0,"scope":"Existing institution-qualified enrollment rows compared against pinned PPEF. Four-key agreement corroborates enrollment identity, not site, legal ownership, current active status or a confirmed purchasing relationship. Alternate-key counts do not create links."}

def plan(national,ledger):
    pins={}
    for k in INPUT_KEYS:
        rows=[r for r in ledger["receipts"] if r["key"]==k]
        require(len(rows)==1 and rows[0]["observations"]==EXPECTED_INPUT[k],"input archive pin/count")
        pins[k]=rows[0]
    inputs={"base_receipt_sha256":national["receipt_sha256"],"national_database_sha256":national["receipt"]["database_sha256"],"policy_version":1,"archives":{k:{"source_sha256":p["source_sha256"],"database_sha256":next(f["sha256"] for f in p["files"] if f["path"]=="projection.sqlite3"),"observations":p["observations"]} for k,p in pins.items()}}
    meta={"kind":KIND,"inputs":inputs,"sha256":hashlib.sha256(a.encode(inputs)).hexdigest()}
    return pins,meta
def restore(store,national,pin,out):
    prefix=storage.prefix_for(pin["key"],pin["source_sha256"]);rec,digest,head=ext.read_small(store,prefix+"/complete.json")
    audit.source_matches(rec,pin,national)
    file=next(x for x in pin["files"] if x["path"]=="projection.sqlite3")
    ext.fetch_verified(store,prefix+"/files/projection.sqlite3",file,out)
    require(ext.read_small(store,prefix+"/complete.json",digest)[2]==head,"input receipt changed")
    with closing(readonly(out)) as db:check_integrity(db)
    return file["sha256"]
def run(store):
    national=storage.national_manifest(store)
    ledger=json.loads(audit.LEDGER.read_text());audit.totals(ledger)
    pins,meta=plan(national,ledger)
    existing=storage.existing(store,KEY,meta["sha256"])
    if existing is not None:
        require(existing["publisher"]==meta and existing["summary"]["stored_enrollment_evidence_rows"]==EXPECTED_TOTAL and existing["base_receipt_sha256"]==national["receipt_sha256"],"existing projection mismatch")
        return existing
    with tempfile.TemporaryDirectory(prefix="pecos-ppef-corroboration-") as d:
        root=Path(d);base,_=ext.restore_national(store,national,root/"national")
        paths={k:root/(k+".sqlite3") for k in INPUT_KEYS}
        for k,p in paths.items():restore(store,national,pins[k],p)
        with closing(readonly(base)) as orig,closing(readonly(paths[INPUT_KEYS[0]])) as cand,closing(readonly(paths[INPUT_KEYS[1]])) as hha,closing(readonly(paths[INPUT_KEYS[2]])) as hospice,closing(readonly(paths[INPUT_KEYS[3]])) as ppef:
            require(scalar(orig,"SELECT count(*) FROM pecos_enrollment_rows")==23521 and scalar(cand,"SELECT count(*) FROM candidates")==23520,"national input count")
            for k,db in ((INPUT_KEYS[1],hha),(INPUT_KEYS[2],hospice),(INPUT_KEYS[3],ppef)):
                require(scalar(db,"SELECT count(*) FROM enrollment_observations")==EXPECTED_INPUT[k],"supplemental input count")
            require(scalar(ppef,"SELECT count(DISTINCT enrollment_id) FROM enrollment_observations")==EXPECTED_INPUT[INPUT_KEYS[3]],"PPEF unique ID")
            from itertools import chain
            rows=chain(national_rows(orig,cand),postacute_rows(hha,INPUT_KEYS[1]),postacute_rows(hospice,INPUT_KEYS[2]))
            out=root/"projection.sqlite3";summary=projection(out,ppef,rows,EXPECTED_TOTAL)
        require(sha(base)==meta["inputs"]["national_database_sha256"] and all(sha(p)==meta["inputs"]["archives"][k]["database_sha256"] for k,p in paths.items()),"input mutated")
        evidence={"publisher":meta,"summary":summary,"projection_sha256":sha(out),"projection_bytes":out.stat().st_size,"public_promotion":False,"reuse_review":"pending"}
        receipt=storage.publish(store,KEY,meta,out,evidence,root,national)
    ext.unchanged(store,national)
    return receipt
def main():
    p=argparse.ArgumentParser();p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ);store=storage.SourceAzure(os.environ)
    try:rec=run(store)
    finally:store.close()
    with args.receipt.open("xb") as f:f.write(a.encode(rec))
    print("PRIVATE_PECOS_PPEF_CORROBORATION_COMPLETE",json.dumps(rec,sort_keys=True),flush=True)
if __name__=="__main__":main()
