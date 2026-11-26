"""Private, versioned extension of a verified FacilitySignal Azure national release.

Reconstruct approved source-native projections, not raw archives. No private
data is served to Pages. Keep original national pointer and bytes immutable.
Only create new extension blobs inside the authorized FacilitySignal prefix.
"""
import argparse,hashlib,io,json,re,sqlite3,tempfile,zipfile
from collections import Counter
from contextlib import closing
from pathlib import Path,PurePosixPath
import openpyxl
import azure_national_archive as archive
from build_combined import require,readonly,sha,check_integrity
from restore_snapshot import LOCK,load_lock as load_national_lock,audit_db
from scripts.verify_expanded_source_archive import load_lock
from scripts import qualify_expanded_cms_integration as cms
from scripts import qualify_qcor_provider as qp,qualify_qcor_expansion as qe
from scripts.probe_qcor_icf_tag_domain import fetch_domain
from scripts import qualify_fda_mqsa as fda

ROOT=Path(__file__).resolve().parents[1]
EXT_POINTER=archive.PREFIX+"/pointers/extension-current.json"
EXT_DOMAIN="FACILITYSIGNAL_PRIVATE_EXTENSION"
MAX_METADATA=2*1024**2
MAX_DB=archive.MAX_DB
MAX_TOTAL=2*1024**3
EXPECTED_ROWS=865809
QCOR_ROWS=628073
FDA_ROWS=9146
HRSA_SCREENED=16657
QCOR_KEYS={k:v[0] for k,v in {**qp.SOURCES,**qe.SOURCES}.items()}

def extension_name(name):
    if name==EXT_POINTER:return name
    require(isinstance(name,str) and name.startswith(archive.PREFIX+"/") and all(x not in ("",".","..") for x in name.split("/")) and not any(ord(x)<32 or x in "\\:" for x in name),"unsafe extension path")
    require(re.fullmatch(re.escape(archive.PREFIX)+r"/releases/extension-[0-9]+-[0-9]+/(?:files(?:/[A-Za-z0-9_.-]+)?|complete\.json)",name) is not None,"outside extension namespace")
    return name

class ExtensionAzure(archive.Azure):
    def blob(self,name):
        if name==EXT_POINTER or "/releases/extension-" in name:extension_name(name)
        else:archive.allowed_name(name)
        return self.container.get_blob_client(name)
    def create(self,name,stream,size,kind):
        extension_name(name)
        return super().create(name,stream,size,kind)
    def delete_probe(self,name,etag):
        raise ValueError("extension migration never deletes blobs")
    def list(self,prefix):
        if "/releases/extension-" in prefix:extension_name(prefix)
        else:archive.allowed_name(prefix)
        for p in self.container.list_blobs(name_starts_with=prefix+"/",include=["metadata"]):
            yield {"name":p.name,"bytes":p.size,"etag":str(p.etag),"folder":str((p.metadata or {}).get("hdi_isfolder","")).lower()=="true"}

def read_small(store,name,expected_sha=None):
    before=store.head(name)
    require(0<before["bytes"]<=MAX_METADATA,"metadata size bound")
    data=bytearray()
    for part in store.chunks(name,before["etag"]):
        data.extend(part)
        require(len(data)<=before["bytes"],"metadata size drift")
    require(len(data)==before["bytes"] and store.head(name)==before,"metadata read changed")
    digest=hashlib.sha256(data).hexdigest()
    require(expected_sha is None or digest==expected_sha,"metadata checksum mismatch")
    return json.loads(data),digest,before

def national_manifest(store):
    store.private()
    pointer,pointer_sha,head=read_small(store,archive.POINTER)
    require(pointer["format_version"]==1 and pointer["domain"]=="FACILITYSIGNAL_NATIONAL_ARCHIVE" and pointer["source_records"]==1904060,"national pointer scope")
    release=pointer["release"]
    require(re.fullmatch(r"bootstrap-[0-9]+-[0-9]+",release) is not None and re.fullmatch(r"[a-f0-9]{40}",pointer["commit"]) is not None,"national lineage")
    prefix=archive.PREFIX+"/releases/"+release
    require(pointer["receipt"]==prefix+"/complete.json","national receipt path")
    receipt,digest,_=read_small(store,pointer["receipt"],pointer["receipt_sha256"])
    require(receipt["format_version"]==1 and receipt["status"]=="COMPLETE" and receipt["domain"]==pointer["domain"] and receipt["release"]==release and receipt["commit"]==pointer["commit"] and receipt["source_records"]==1904060 and receipt["sha256_readback"] is True and receipt["exact_inventory"] is True,"national receipt mismatch")
    require(receipt["payload_prefix"]==prefix+"/files","national payload path")
    require(receipt["source_lock_sha256"]==sha(LOCK),"national lock changed")
    rows=receipt["files"]
    require(0<len(rows)==receipt["file_count"]<=archive.MAX_FILES and len({x["path"] for x in rows})==len(rows),"national inventory count")
    require(sum(x["bytes"] for x in rows)==receipt["total_bytes"]<=archive.MAX_TOTAL,"national inventory size")
    for x in rows:
        require(re.fullmatch(r"(?:snapshot/(?:facilitysignal\.sqlite3|recovery-audit\.json)|(?:research|web|web/public-directory)/[A-Za-z0-9_.-]+\.json)",x["path"]) is not None,"unexpected national payload file")
        require(type(x["bytes"]) is int and x["bytes"]>0 and re.fullmatch(r"[a-f0-9]{64}",x["sha256"]) is not None,"invalid national payload pin")
    by_path={x["path"]:x for x in rows}
    require({"snapshot/facilitysignal.sqlite3","snapshot/recovery-audit.json"}<=by_path.keys(),"missing database or audit")
    db=by_path["snapshot/facilitysignal.sqlite3"]
    require(db["bytes"]==receipt["database_bytes"]<=MAX_DB and db["sha256"]==receipt["database_sha256"],"national database pin mismatch")
    return {"pointer":pointer,"pointer_sha256":pointer_sha,"pointer_etag":head["etag"],"receipt":receipt,"receipt_sha256":digest,"files":by_path}

def unchanged(store,national):
    require(store.head(archive.POINTER)["etag"]==national["pointer_etag"],"national pointer advanced")
    p,d,_=read_small(store,archive.POINTER)
    require(p==national["pointer"] and d==national["pointer_sha256"],"national pointer changed")
    store.private()

def fetch_verified(store,name,pin,path):
    before=store.head(name)
    require(before["bytes"]==pin["bytes"],"archive payload size mismatch")
    h=hashlib.sha256();n=0
    with path.open("xb") as out:
        for part in store.chunks(name,before["etag"]):
            n+=len(part);require(n<=pin["bytes"],"archive read exceeds pin")
            h.update(part);out.write(part)
    require(n==pin["bytes"] and h.hexdigest()==pin["sha256"] and store.head(name)==before,"archive payload checksum or ETag mismatch")
    require(sha(path)==pin["sha256"],"local readback hash mismatch")

def restore_national(store,national,root):
    receipt=national["receipt"];payload=receipt["payload_prefix"]
    root.mkdir(mode=0o700)
    for key in ("facilitysignal.sqlite3","recovery-audit.json"):
        f="snapshot/"+key;fetch_verified(store,payload+"/"+f,national["files"][f],root/key)
    local=root/"facilitysignal.sqlite3"
    a=json.loads((root/"recovery-audit.json").read_text())
    require(a["database_sha256"]==sha(local)==receipt["database_sha256"] and a["database_bytes"]==local.stat().st_size and a["source_lock_sha256"]==receipt["source_lock_sha256"],"restored database/audit mismatch")
    require(audit_db(local,load_national_lock(LOCK))==a["table_counts"] and a["source_records_total"]==1904060,"restored national source reconciliation")
    with closing(readonly(local)) as db:
        check_integrity(db)
        for table,n in {"iqies_capability_observations":68604,"qies_hospital_service_observations":163176,"iqies_status_observations":100334,"facility_registry_candidate":47169}.items():
            require(db.execute("SELECT count(*) FROM "+table).fetchone()[0]==n,"restored derived count mismatch")
    require(sha(local)==receipt["database_sha256"],"restored base mutated")
    unchanged(store,national)
    return local,a

def verify_qcor_pin(path,pin):
    require(path.stat().st_size==pin["bytes"] and sha(path)==pin["sha256"],"QCOR workbook release changed")
    with zipfile.ZipFile(path) as z:
        require(len(z.infolist())<=2000 and sum(x.file_size for x in z.infolist())<=2_000_000_000 and "xl/workbook.xml" in z.namelist(),"QCOR workbook expansion bound")

def download_qcor(path,pin):
    from scripts.probe_qcor_hospital import request
    url=pin["url"]
    require(re.fullmatch(r"https://qcor\.cms\.gov/download[A-Za-z0-9_-]*2567",url) and 0<pin["bytes"]<=350_000_000,"QCOR source URL or size")
    n=0
    with request(url,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") as res,path.open("xb") as out:
        require(res.geturl()==url,"QCOR redirect")
        while chunk:=res.read(1024*1024):
            n+=len(chunk);require(n<=pin["bytes"],"QCOR source size exceeded")
            out.write(chunk)
    verify_qcor_pin(path,pin)

def icf_domain(pin):
    domains,metadata=fetch_domain()
    require(len(domains)==1,"ICF selector ambiguous")
    domain=domains[0]
    p=pin["required_domain"]
    require(metadata["url"]==p["url"] and len(domain)==p["code_count"] and hashlib.sha256("\n".join(sorted(domain)).encode()).hexdigest()==p["sorted_code_sha256"],"ICF selector changed")
    return domain

def init_extension(db):
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("CREATE TABLE extension_sources(source_id TEXT PRIMARY KEY,table_name TEXT NOT NULL,source_sha256 TEXT NOT NULL,source_bytes INTEGER NOT NULL,rows INTEGER NOT NULL,qualification_run INTEGER NOT NULL)")
    db.execute("CREATE TABLE qcor_provider_rows(source_id TEXT NOT NULL,ordinal INTEGER NOT NULL,ccn TEXT NOT NULL,event TEXT NOT NULL,day TEXT NOT NULL,kind TEXT NOT NULL,PRIMARY KEY(source_id,ordinal),FOREIGN KEY(source_id) REFERENCES extension_sources(source_id)) WITHOUT ROWID")
    db.execute("CREATE INDEX qcor_provider_key ON qcor_provider_rows(source_id,ccn,day)")
    db.commit()

def compare_qcor(prior,result):
    fields=("header","columns","field_mapping","input_rows","stored_rows","rejected_rows","blank_rows","row_kinds","distinct_provider_keys","distinct_survey_event_keys","events_with_nonmemo_tag","events_without_nonmemo_tag")
    require(all(result[k]==prior[k] for k in fields),"QCOR prior qualification mismatch")
    return len(fields)

def load_qcor(db,path,key,pin,prior,domain=None):
    verify_qcor_pin(path,pin)
    sid=QCOR_KEYS[key]
    require(sid==pin["source_id"]==prior["source_id"] and prior["mapping_complete"] and prior["rejected_rows"]==0,"QCOR prior evidence scope")
    require(key!="icf" or domain is not None,"ICF domain required")
    expected=pin["qualified_rows"]
    db.execute("INSERT INTO extension_sources VALUES(?,?,?,?,?,?)",(sid,"qcor_provider_rows",pin["sha256"],pin["bytes"],expected,pin["qualification_run"]))
    counts=Counter();total=blank=0;batch=[]
    book=openpyxl.load_workbook(path,read_only=True,data_only=True,keep_links=False)
    try:
        require(len(book.worksheets)==1,"QCOR sheet count")
        sheet=book.worksheets[0];sheet.reset_dimensions()
        rows=iter(sheet.iter_rows(values_only=True));header=tuple(next(rows,()))
        require(list(header)==prior["header"],"QCOR source header differs")
        m=qp.map_header(header)
        require(set(m)==set(qp.ALIASES),"QCOR mapping")
        for ordinal,values in enumerate(rows,2):
            require(ordinal<=1_500_001,"QCOR row bound")
            if not any(v is not None and v!="" for v in values):blank+=1;continue
            total+=1
            require(len(values)<=len(header),"QCOR row width")
            c,e,d,k=qp.classify(values,m,key) if key in qp.SOURCES else qe.classify(values,m,key,domain)
            batch.append((sid,ordinal,c,e,d,k));counts[k]+=1
            if len(batch)>=5000:
                db.executemany("INSERT INTO qcor_provider_rows VALUES(?,?,?,?,?,?)",batch);batch.clear()
        if batch:db.executemany("INSERT INTO qcor_provider_rows VALUES(?,?,?,?,?,?)",batch)
    finally:book.close()
    def scalar(sql):return db.execute(sql,(sid,)).fetchone()[0]
    stored=scalar("SELECT count(*) FROM qcor_provider_rows WHERE source_id=?")
    providers=scalar("SELECT count(DISTINCT ccn) FROM qcor_provider_rows WHERE source_id=?")
    events=scalar("SELECT count(*) FROM (SELECT DISTINCT ccn,event,day FROM qcor_provider_rows WHERE source_id=?)")
    tagged=scalar("SELECT count(*) FROM (SELECT DISTINCT ccn,event,day FROM qcor_provider_rows WHERE source_id=? AND kind='nonmemo_tag')")
    require(total==stored==expected==pin["input_rows"]==sum(counts.values()),"QCOR row reconciliation")
    result={"header":list(header),"columns":len(header),"field_mapping":{k:header[i] for k,i in m.items()},"input_rows":total,"stored_rows":stored,"rejected_rows":0,"blank_rows":blank,"row_kinds":dict(counts),"distinct_provider_keys":providers,"distinct_survey_event_keys":events,"events_with_nonmemo_tag":tagged,"events_without_nonmemo_tag":events-tagged}
    compared=compare_qcor(prior,result);db.commit()
    return {"table":"qcor_provider_rows","rows":stored,"distinct_source_provider_keys":providers,"source_event_keys":events,"stable_audit_fields_compared":compared,"source_sha256":pin["sha256"],"original_qualification_run":pin["qualification_run"]}

def load_fda(db,path,pin,prior):
    require(path.stat().st_size==pin["bytes"] and sha(path)==pin["sha256"],"FDA release changed")
    result=fda.audit_archive(db,path,allow_pinned_width_exception=True)
    keys=[k for k in result if k in prior and k!="limits"]
    require(result["stored_rows"]==pin["qualified_rows"]==FDA_ROWS and result["unresolved_rows"]==0 and all(result[k]==prior[k] for k in keys),"FDA prior qualification mismatch")
    db.execute("INSERT INTO extension_sources VALUES(?,?,?,?,?,?)",(pin["source_id"],"mqsa_projection",pin["sha256"],pin["bytes"],FDA_ROWS,pin["qualification_run"]))
    db.commit()
    return {"table":"mqsa_projection","rows":FDA_ROWS,"stable_audit_fields_compared":len(keys),"source_sha256":pin["sha256"],"original_qualification_run":pin["qualification_run"]}

def build_extension(base,output):
    require(not output.exists(),"extension DB exists")
    lock=load_lock();pins={x["source_id"]:x for x in lock["expanded_sources"]}
    ledger=json.loads((ROOT/"research/coverage_status.json").read_text())
    base_sha=sha(base);out={}
    with tempfile.TemporaryDirectory(prefix="extension-source-") as tmp,closing(readonly(base)) as original,closing(sqlite3.connect(output)) as db:
        root=Path(tmp)
        init_extension(db)
        providers=cms.provider_sets(original)
        for sid in cms.SOURCES:
            pin=pins[sid];data=cms.download(pin)
            out[sid]=cms.project_one(sid,data,pin,cms.prior_audits(ledger)[sid],db,providers)
            del data
            print("AZURE_EXTENSION_SOURCE",sid,json.dumps(out[sid],sort_keys=True),flush=True)
        for key,sid in sorted(QCOR_KEYS.items(),key=lambda x:x[1]):
            pin=pins[sid]
            group="qcor_provider_qualified_baselines" if key in qp.SOURCES else "qcor_expansion_qualified_baselines"
            prior=ledger[group][key]["audit"]
            domain=icf_domain(pin) if key=="icf" else None
            path=root/"source.xlsx"
            download_qcor(path,pin)
            out[sid]=load_qcor(db,path,key,pin,prior,domain)
            path.unlink()
            print("AZURE_EXTENSION_SOURCE",sid,json.dumps(out[sid],sort_keys=True),flush=True)
        pin=pins["FS-011"];path=root/"fda.zip";fda.download(path)
        out["FS-011"]=load_fda(db,path,pin,ledger["fda_mqsa_qualified_baseline"]["audit"])
        path.unlink()
        require(set(out)==set(pins)-{"FS-009"} and sum(x["rows"] for x in out.values())==EXPECTED_ROWS,"extension coverage")
        require(db.execute("SELECT count(*),sum(rows) FROM extension_sources").fetchone()==(16,EXPECTED_ROWS),"lineage count")
        require(db.execute("SELECT count(*) FROM qcor_provider_rows").fetchone()[0]==QCOR_ROWS,"QCOR total")
        require(dict(db.execute("SELECT source_id,count(*) FROM qcor_provider_rows GROUP BY source_id"))=={sid:out[sid]["rows"] for sid in QCOR_KEYS.values()},"QCOR per-source count")
        require(db.execute("SELECT count(*) FROM mqsa_projection").fetchone()[0]==FDA_ROWS,"FDA total")
        require(cms.surveys.compare_dates(db,original)=={"same_ccn_day":619069},"original citation crosscheck")
        check_integrity(db);db.commit()
    require(sha(base)==base_sha,"national database changed")
    return {"source_records":EXPECTED_ROWS,"source_count":16,"sources":out,"qcor_source_rows":QCOR_ROWS,
            "cms_csv_source_rows":cms.TOTAL,"fda_source_rows":FDA_ROWS,
            "hrsa_aggregate_screened_rows":HRSA_SCREENED,"hrsa_row_level_records":0,
            "base_database_sha256":base_sha,"database_bytes":output.stat().st_size,"database_sha256":sha(output),
            "scope":"Private source-native extension tables. No canonical site inference, raw data archive, personal contact fields, survey narratives, HRSA site rows, NPPES or HCRIS cell rows. All commercial reuse review states remain unchanged."}

def publish(store,release,commit,national,db_path,db_audit,root):
    require(re.fullmatch(r"extension-[0-9]+-[0-9]+",release) and re.fullmatch(r"[a-f0-9]{40}",commit),"extension lineage")
    unchanged(store,national)
    require(not store.exists(EXT_POINTER),"extension pointer exists; no overwrite")
    require(db_audit["database_sha256"]==sha(db_path) and db_audit["database_bytes"]==db_path.stat().st_size<=MAX_DB and db_audit["base_database_sha256"]==national["receipt"]["database_sha256"] and db_audit["source_records"]==EXPECTED_ROWS,"extension audit mismatch")
    audit_path=root/"extension-audit.json"
    audit_path.write_bytes(archive.encode(db_audit))
    files={"extension.sqlite3":db_path,"extension-audit.json":audit_path,"expanded-source-lock.json":ROOT/"research/expanded_source_lock_20261126.json"}
    records=[archive.rec(k,v) for k,v in sorted(files.items())]
    require(sum(r["bytes"] for r in records)<=MAX_TOTAL,"extension transfer bound")
    prefix=archive.PREFIX+"/releases/"+release
    payload=prefix+"/files";etags={}
    for r in records:
        name=payload+"/"+r["path"];extension_name(name)
        with files[r["path"]].open("rb") as f:
            store.create(name,f,r["bytes"],"application/json" if name.endswith(".json") else "application/octet-stream")
        etags[name]=archive.verify(store,name,r)
        require(sha(files[r["path"]])==r["sha256"],"local payload mutated")
    archive.check_inventory(store,payload,records,etags)
    receipt={"format_version":1,"status":"COMPLETE","domain":EXT_DOMAIN,"release":release,"commit":commit,"base_release":national["pointer"]["release"],"base_receipt_sha256":national["receipt_sha256"],"base_pointer_sha256":national["pointer_sha256"],"payload_prefix":payload,"source_records":EXPECTED_ROWS,"base_source_records":1904060,"source_count":16,"database_sha256":db_audit["database_sha256"],"database_bytes":db_audit["database_bytes"],"files":records,"file_count":len(records),"total_bytes":sum(r["bytes"] for r in records),"sha256_readback":True,"exact_inventory":True,"scope":db_audit["scope"]}
    data=archive.encode(receipt);name=prefix+"/complete.json";archive.put_bytes(store,name,data)
    archive.check_inventory(store,payload,records,etags);unchanged(store,national)
    pointer={"format_version":1,"domain":EXT_DOMAIN,"release":release,"commit":commit,"base_release":receipt["base_release"],"base_receipt_sha256":receipt["base_receipt_sha256"],"receipt":name,"receipt_sha256":hashlib.sha256(data).hexdigest(),"source_records":EXPECTED_ROWS}
    archive.put_bytes(store,EXT_POINTER,archive.encode(pointer))
    unchanged(store,national)
    return receipt

def main():
    import os
    p=argparse.ArgumentParser();p.add_argument("--receipt",type=Path,required=True);a=p.parse_args()
    require(not a.receipt.exists(),"receipt exists")
    run,commit=archive.run_key(os.environ);release=run.replace("bootstrap-","extension-",1)
    store=ExtensionAzure(os.environ)
    try:
        national=national_manifest(store)
        require(not store.exists(EXT_POINTER),"extension pointer exists; no overwrite")
        with tempfile.TemporaryDirectory(prefix="azure-extension-") as d:
            root=Path(d);base,audit=restore_national(store,national,root/"national")
            print("AZURE_NATIONAL_RESTORE_VERIFIED",json.dumps({"release":national["pointer"]["release"],"source_records":audit["source_records_total"],"database_sha256":audit["database_sha256"]}),flush=True)
            path=root/"extension.sqlite3";result=build_extension(base,path)
            receipt=publish(store,release,commit,national,path,result,root)
        a.receipt.write_bytes(archive.encode(receipt))
        print("FACILITYSIGNAL_AZURE_EXTENSION_COMPLETE",json.dumps({k:v for k,v in receipt.items() if k!="files"},sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
