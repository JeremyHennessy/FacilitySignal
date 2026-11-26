"""Archive the current CMS PPEF Enrollment sub-file with Type 2 NPI corroboration.

Retain only institutional identifiers and source-native provider specialty code.
Never retain individual names, locations, reassignments or unmatched identifiers.
"""
import argparse,csv,hashlib,json,os,re,sqlite3,tempfile,zipfile
from collections import Counter
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
import azure_national_archive as a
import collect_registry as registry
from scripts import azure_source_archive as storage,archive_pecos_nppes_candidates as identity
from scripts.archive_postacute_enrollments import restore_input
from build_combined import require,sha,readonly,check_integrity
TITLE="Medicare Fee-For-Service Public Provider Enrollment"
KEY="ppef-type2-enrollment"
FIELDS=("NPI","PECOS_ASCT_CNTL_ID","ENRLMT_ID","PROVIDER_TYPE_CD")
MAX_DOWNLOAD=550_000_000
MAX_EXPANDED=2_500_000_000
MAX_ROWS=12_000_000

def catalog_selection(catalog):
    series=[x for x in catalog.get("datasetSeries",[]) if x.get("title")==TITLE]
    if series:
        require(len(series)==1 and isinstance(series[0].get("last"),dict),"PPEF series ambiguity")
        version=series[0]["last"].get("@id");require(isinstance(version,str) and version,"PPEF series version")
        datasets=[d for d in catalog["dataset"] if d.get("@id")==version]
        require(len(datasets)==1,"PPEF version dataset ambiguity")
        d=datasets[0];distributions=[x for x in d.get("distribution",[]) if x.get("resourcesAPI")]
        # Several distributions may repeat the same resourcesAPI; require one distinct URL.
    else:
        datasets=[d for d in catalog["dataset"] if d.get("title")==TITLE]
        require(len(datasets)==1,"PPEF legacy catalog ambiguity")
        d=datasets[0];version=d.get("@id") or d.get("identifier")
        distributions=[x for x in d.get("distribution",[]) if x.get("format")=="API" and x.get("description")=="latest" and x.get("resourcesAPI")]
    require(d.get("accessLevel")=="public","PPEF public resource")
    urls={registry.allowed(x["resourcesAPI"]) for x in distributions}
    require(len(urls)==1 and isinstance(version,str) and version,"PPEF version resource API")
    return {"catalog_version":version,"title":TITLE,"modified":d.get("modified"),"resource_api":urls.pop(),"landing":d.get("landingPage"),"license":d.get("license")}

def resource_selection(resources):
    rows=resources.get("data") if isinstance(resources,dict) else None
    require(isinstance(rows,list) and 0<len(rows)<=100,"PPEF resource metadata")
    candidates=[]
    for x in rows:
        require(isinstance(x,dict),"PPEF resource shape")
        name=x.get("name","")
        if isinstance(name,str) and re.search(r"\benrollment\s+sub[- ]file\b",name,re.I) and not re.search(r"\b(data dictionary|methodology|reassignment|additional|location|secondary)\b",name,re.I):
            candidates.append(x)
    require(len(candidates)==1,"missing/ambiguous PPEF Enrollment Sub-File")
    x=candidates[0];url=registry.allowed(x["downloadURL"])
    path=urlsplit(url).path.lower()
    require(path.endswith((".csv",".zip")),"PPEF CSV or ZIP resource")
    return {"resource_name":x["name"],"url":url,"zipped":path.endswith(".zip"),"resource_id":x.get("id") or x.get("identifier") or x.get("@id")}

def discover():
    result=catalog_selection(registry.get_json(registry.CATALOG))
    return {**result,**resource_selection(registry.get_json(result["resource_api"]))}

def download(meta,path):
    h=hashlib.sha256();n=0
    with registry.response(meta["url"],"application/zip" if meta["zipped"] else "text/csv") as res,path.open("xb") as out:
        require(res.geturl()==meta["url"],"unexpected source redirect")
        length=res.headers.get("Content-Length")
        if length:require(0<int(length)<=MAX_DOWNLOAD,"source transfer bound")
        while chunk:=res.read(1024*1024):
            n+=len(chunk);require(n<=MAX_DOWNLOAD,"source transfer bound");h.update(chunk);out.write(chunk)
        require(n>0 and (not length or n==int(length)),"source transfer length")
        return {**meta,"bytes":n,"sha256":h.hexdigest(),"etag":res.headers.get("ETag"),"last_modified":res.headers.get("Last-Modified")}

def check_zip(path):
    with zipfile.ZipFile(path) as z:
        members=z.infolist();files=[m for m in members if not m.is_dir() and m.filename.lower().endswith(".csv")]
        require(0<len(members)<=12 and len(files)==1 and 0<sum(m.file_size for m in members)<=MAX_EXPANDED and not files[0].flag_bits&1,"PPEF archive structure")

def project(path,zipped,reg_path,out):
    if zipped:check_zip(path)
    enc=registry.source_encoding(path,zipped);counts=Counter();codes=Counter()
    with closing(readonly(reg_path)) as reg,closing(sqlite3.connect(out)) as db:
        db.execute("CREATE TABLE enrollment_observations(ordinal INTEGER PRIMARY KEY,enrollment_id TEXT NOT NULL UNIQUE,pac_id TEXT NOT NULL,npi TEXT NOT NULL,provider_type_code TEXT NOT NULL)")
        with registry.open_csv(path,zipped,enc) as f:
            reader=csv.reader(f,strict=True);header=next(reader)
            normalized=[x.strip().upper() for x in header]
            require(0<len(header)<=200 and len(set(normalized))==len(normalized) and set(FIELDS)<=set(normalized),"PPEF documented enrollment schema")
            cols={k:normalized.index(k) for k in FIELDS};batch=[]
            for ordinal,row in enumerate(reader,2):
                counts["input_rows"]+=1
                require(counts["input_rows"]<=MAX_ROWS and len(row)==len(header),"PPEF row bound or width")
                npi=row[cols["NPI"]].strip()
                if not identity.npi_valid(npi):
                    counts["invalid_or_missing_npi"]+=1;continue
                if reg.execute("SELECT 1 FROM organization_fields WHERE npi=?",(npi,)).fetchone() is None:
                    counts["not_in_type2_reference"]+=1;continue
                pac=row[cols["PECOS_ASCT_CNTL_ID"]].strip();enrollment=row[cols["ENRLMT_ID"]].strip();code=row[cols["PROVIDER_TYPE_CD"]].strip()
                if not(re.fullmatch(r"[0-9]{1,10}",pac) and re.fullmatch(r"[A-Za-z0-9]{15}",enrollment) and re.fullmatch(r"[0-9]{2}-[0-9]{2}",code)):
                    counts["institutional_key_or_code_review"]+=1;continue
                batch.append((ordinal,enrollment,pac,npi,code));counts["stored_rows"]+=1;codes[code]+=1
                if len(batch)>=5000:db.executemany("INSERT INTO enrollment_observations VALUES(?,?,?,?,?)",batch);batch.clear()
            if batch:db.executemany("INSERT INTO enrollment_observations VALUES(?,?,?,?,?)",batch)
        require(counts["input_rows"]==counts["stored_rows"]+counts["invalid_or_missing_npi"]+counts["not_in_type2_reference"]+counts["institutional_key_or_code_review"] and counts["stored_rows"]>0,"PPEF row reconciliation")
        require(sum(codes.values())==counts["stored_rows"],"provider type reconciliation")
        # An independent complete CSV pass verifies record count, without collecting identifiers.
        with registry.open_csv(path,zipped,enc) as f:
            independent=csv.reader(f,strict=True);require(next(independent)==header,"header drift")
            second=sum(1 for _ in independent)
        require(second==counts["input_rows"],"independent record count")
        db.execute("CREATE INDEX enrollment_npi ON enrollment_observations(npi)")
        db.execute("CREATE INDEX enrollment_pac ON enrollment_observations(pac_id)")
        db.execute("CREATE INDEX enrollment_provider_type ON enrollment_observations(provider_type_code)")
        db.commit();check_integrity(db)
        require(db.execute("SELECT count(*) FROM enrollment_observations").fetchone()[0]==counts["stored_rows"],"PPEF stored count")
        return {**dict(counts),"source_columns":len(header),"independent_csv_count":second,"encoding":enc,"provider_type_counts":dict(codes),"distinct_type2_npis":db.execute("SELECT count(DISTINCT npi) FROM enrollment_observations").fetchone()[0],"individual_or_unmatched_identifiers_retained":0,"names_addresses_contacts_retained":0,"public_promotion":False,"scope":"PPEF Enrollment sub-file; exact November 2026 Type 2 NPI membership only. No additional NPIs, reassignment or location files, historical/current status inference or canonical site identity."}

def main():
    p=argparse.ArgumentParser();p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ)
    store=storage.SourceAzure(os.environ)
    try:
        national=storage.national_manifest(store);meta=discover()
        with tempfile.TemporaryDirectory(prefix="ppef-enrollment-") as d:
            root=Path(d);source=root/"source";publisher=download(meta,source)
            require(discover()==meta and sha(source)==publisher["sha256"],"PPEF publisher/source drift")
            receipt=storage.existing(store,KEY,publisher["sha256"])
            if receipt is None:
                reg=root/"nppes.sqlite3"
                reference=restore_input(store,national,"nppes-monthly",identity.NPPES_PIN,identity.NPPES_DB_PIN,reg)
                require(reference["summary"]["organization_observations"]==1990237,"NPPES reference count")
                out=root/"projection.sqlite3";summary=project(source,meta["zipped"],reg,out)
                require(sha(source)==publisher["sha256"] and sha(reg)==identity.NPPES_DB_PIN,"input bytes changed");source.unlink()
                summary["nppes_database_sha256"]=identity.NPPES_DB_PIN
                audit={"publisher":publisher,"summary":summary,"projection_sha256":sha(out),"projection_bytes":out.stat().st_size,"reuse_review":"pending","public_promotion":False}
                receipt=storage.publish(store,KEY,publisher,out,audit,root,national)
        with args.receipt.open("xb") as f:f.write(a.encode(receipt))
        print("PRIVATE_PPEF_ENROLLMENT_COMPLETE",json.dumps(receipt,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
