"""HCRIS modern-form report indexes, with complete streamed child-row audit.

Keep only report keys, source ordinal, per-report child counts and aggregate
coordinate/value-shape evidence. Do not retain alpha text or interpret measures.
Large forms deliberately use an index projection; not full numeric archival.
"""
import argparse,csv,hashlib,io,json,os,re,sqlite3,tempfile,zipfile
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlsplit
import azure_national_archive as a
from build_combined import require,sha,check_integrity
from scripts import azure_source_archive as storage,qualify_hcris_hha as h
BASE="https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/"
TARGETS={
 "hospital":("hospital-2024-index","CMS-2552-10","cost-reports-fiscal-year/hospital-2010-fy-2024","HOSPITAL-2010 FY 2024 DATA FILES"),
 "snf":("snf-2024-index","CMS-2540-10","cost-reports-fiscal-year/snf-2010-fy-2024-data-files","SNF-2010 FY 2024 DATA FILES"),
 "hospice":("hospice-2014-index","CMS-1984-14","hospice-1984-2014-form","Hospice 14 Data files"),
 "renal":("renal-2011-index","CMS-265-11","renal-facility-265-2011-form","Renal 2011 Data files"),
 "fqhc":("fqhc-2014-index","CMS-224-14","fqhc-224-2014-form","FQHC14 Data files"),
 "rhc":("rhc-2017-index","CMS-222-17","rural-health-center-222-2017-form","RHC Data Files"),
 "cmhc":("cmhc-2017-index","CMS-2088-17","cmhc-2088-2017-form","CMHC17 Data files")}
MAX_DOWNLOAD=650_000_000
MAX_EXPANDED=6_000_000_000
MAX_ROWS=70_000_000

def resolve(html,page,label):
    parser=h.Links();parser.feed(html)
    wanted=label.casefold()
    matches={h.allowed(urljoin(page,href)) for href,text in parser.links if re.sub(r"\s*\(zip\)$","",text,flags=re.I).casefold()==wanted}
    require(len(matches)==1,"official form data link missing/ambiguous")
    url=matches.pop();require(urlsplit(url).path.casefold().endswith(".zip"),"publisher data ZIP required")
    return url

def discover(target):
    _,form,slug,label=TARGETS[target];page=BASE+slug
    with h.request(page) as res:
        raw=res.read(5_000_001);require(0<len(raw)<=5_000_000,"CMS landing size")
    return {"landing":page,"url":resolve(raw.decode("utf-8",errors="strict"),page,label),"form":form,"scope":"FY2024" if target in ("hospital","snf") else "publisher multi-year modern form"}

def download(meta,path):
    digest=hashlib.sha256();size=0
    with h.request(meta["url"]) as res,path.open("xb") as f:
        final=h.allowed(res.geturl());require(urlsplit(final).path.casefold().endswith(".zip"),"final source ZIP")
        length=res.headers.get("Content-Length")
        if length:require(0<int(length)<=MAX_DOWNLOAD,"compressed archive bound")
        while chunk:=res.read(1024*1024):
            size+=len(chunk);require(size<=MAX_DOWNLOAD,"compressed archive bound");digest.update(chunk);f.write(chunk)
        require(size>0 and (not length or size==int(length)),"source transfer length")
        return {**meta,"final_url":final,"bytes":size,"sha256":digest.hexdigest(),"etag":res.headers.get("ETag"),"last_modified":res.headers.get("Last-Modified"),"retrieved_at":datetime.now(timezone.utc).isoformat()}

def members(z):
    files=[i for i in z.infolist() if not i.is_dir()]
    require(0<len(files)<=20 and 0<sum(i.file_size for i in files)<=MAX_EXPANDED,"archive expansion bound")
    roles={}
    for info in files:
        name=Path(info.filename).name.casefold()
        if not name.endswith((".csv",".txt")):continue
        role="alpha" if "alphnmrc" in name or "alpha" in name else "numeric" if "nmrc" in name or "numeric" in name else "report" if "rpt" in name or "report" in name else None
        if role:
            require(role not in roles and not info.flag_bits&1,"ambiguous or encrypted member")
            roles[role]=info
    require(set(roles)=={"report","numeric","alpha"},"relational member set")
    return roles

def project(path,db_path):
    with zipfile.ZipFile(path) as z,closing(sqlite3.connect(db_path)) as db:
        roles=members(z);keys={};widths=Counter()
        with z.open(roles["report"]) as raw,io.TextIOWrapper(raw,encoding="latin-1",newline="") as f:
            for ordinal,row in enumerate(csv.reader(f,strict=True),1):
                require(ordinal<=150000 and 2<=len(row)<=100,"report row bound")
                key=h.report_key(row[0]);require(key is not None and key not in keys,"report primary key")
                keys[key]=[ordinal,0,0];widths[str(len(row))]+=1
        require(keys and len(widths)==1,"report width consistency")
        summary={"report_rows":len(keys),"report_width_counts":dict(widths),"child_tables":{}}
        for role,slot in (("numeric",1),("alpha",2)):
            shape=Counter();values=Counter();n=0
            with z.open(roles[role]) as raw,io.TextIOWrapper(raw,encoding="latin-1",newline="") as f:
                for n,row in enumerate(csv.reader(f,strict=True),1):
                    require(n<=MAX_ROWS and len(row)==5,"child row width/bound")
                    k=h.report_key(row[0]);require(k in keys,"orphan child report")
                    keys[k][slot]+=1
                    # Report only structural shape categories, not coordinates or actual values.
                    w,l,c=(v.strip() for v in row[1:4])
                    bounded=bool(re.fullmatch(r"[A-Z0-9*]{1,7}",w) and re.fullmatch(r"[0-9A-Z]{1,5}",l) and re.fullmatch(r"[0-9A-Z]{1,5}",c))
                    shape["bounded_source_coordinate" if bounded else "coordinate_review"]+=1
                    state=h.cell_state(row[4]) if role=="numeric" else ("present" if row[4].strip() else "blank")
                    values[state]+=1
            require(n>0 and n==sum(shape.values())==sum(values.values())==sum(k[slot] for k in keys.values()),"child reconciliation")
            summary["child_tables"][role]={"rows":n,"coordinate_shapes":dict(shape),"value_states":dict(values),"reports_with_cells":sum(k[slot]>0 for k in keys.values()),"uncompressed_bytes":roles[role].file_size,"zip_crc32":format(roles[role].CRC,"08x")}
        db.execute("CREATE TABLE reports(report_key TEXT PRIMARY KEY,ordinal INTEGER NOT NULL UNIQUE,numeric_rows INTEGER NOT NULL,alpha_rows INTEGER NOT NULL) WITHOUT ROWID")
        db.executemany("INSERT INTO reports VALUES(?,?,?,?)",((key,*v) for key,v in keys.items()))
        db.commit();check_integrity(db)
        observed=db.execute("SELECT count(*),sum(numeric_rows),sum(alpha_rows) FROM reports").fetchone()
        require(observed==(len(keys),summary["child_tables"]["numeric"]["rows"],summary["child_tables"]["alpha"]["rows"]),"stored report index reconciliation")
        return {**summary,"stored_rows":len(keys),"screened_child_rows":observed[1]+observed[2],"numeric_cell_values_retained":0,"alpha_values_retained":0,"report_metadata_fields_retained":["report_key","ordinal"],"retention":"report index with child counts; not full numeric-cell archive","units_interpreted":False,"public_promotion":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--source",choices=TARGETS,required=True);p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ)
    store=storage.SourceAzure(os.environ)
    try:
        national=storage.national_manifest(store);meta=discover(args.source);key="hcris-"+TARGETS[args.source][0]
        with tempfile.TemporaryDirectory(prefix="hcris-form-index-") as d:
            root=Path(d);source=root/"source.zip";publisher=download(meta,source)
            require(discover(args.source)==meta and sha(source)==publisher["sha256"],"publisher link or source bytes drift")
            rec=storage.existing(store,key,publisher["sha256"])
            if rec is None:
                out=root/"projection.sqlite3";summary=project(source,out)
                require(sha(source)==publisher["sha256"],"source mutated");source.unlink()
                audit={"publisher":publisher,"summary":summary,"projection_sha256":sha(out),"projection_bytes":out.stat().st_size,"reuse_review":"pending","public_promotion":False}
                rec=storage.publish(store,key,publisher,out,audit,root,national)
        with args.receipt.open("xb") as f:f.write(a.encode(rec))
        print("PRIVATE_HCRIS_FORM_INDEX_COMPLETE",args.source,json.dumps(rec,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
