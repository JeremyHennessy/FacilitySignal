"""Qualify the official DOL inspection and violation bulk archives.

Separate publisher member/row counts, source edition identity, healthcare
NAICS observations and exact inspection activity-number citation joins.
No establishment names, addresses, individual or injury narratives, or
row-level inspection/citation identities survive the scratch computation.
"""
import argparse,csv,hashlib,io,json,os,re,tempfile,urllib.request,zipfile
from collections import Counter
from datetime import datetime,timezone,date
from pathlib import Path
from urllib.parse import urlsplit
import azure_national_archive as a
from build_combined import require,sha
from scripts import azure_source_archive as storage
from scripts.archive_environment_state import write_aggregate
KEY="osha-enforcement-healthcare-aggregate"
BASE="https://data.dol.gov/data-catalog/OSHA/"
URLS={k:BASE+k+"/OSHA_"+k+".zip" for k in ("inspection","violation")}
DOC="https://usdepartmentoflabor.github.io/Developer/health-and-safety/dol-osha-enforcement/"
MAX_DOWNLOAD={"inspection":2_100_000_000,"violation":2_400_000_000}
MAX_EXPANDED=7_000_000_000
MAX_ROWS={"inspection":8_000_000,"violation":20_000_000}
REQUIRED={"inspection":{"ACTIVITY_NR","NAICS_CODE","SITE_STATE","OPEN_DATE","INSP_SCOPE"},"violation":{"ACTIVITY_NR","CITATION_ID","DELETE_FLAG","VIOL_TYPE"}}
STATES=set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR VI".split())
SECTORS={"621","622","623","624"}
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError("unexpected DOL redirect")
def response(kind,method="GET"):
    url=URLS[kind];req=urllib.request.Request(url,method=method,headers={"User-Agent":"FacilitySignal public source qualification","Accept-Encoding":"identity"})
    return urllib.request.build_opener(NoRedirect()).open(req,timeout=120)
def metadata(res):
    return {"etag":res.headers.get("ETag"),"last_modified":res.headers.get("Last-Modified"),"bytes":int(res.headers["Content-Length"]) if res.headers.get("Content-Length") else None}
def head(kind):
    with response(kind,"HEAD") as r:
        require(r.geturl()==URLS[kind],"DOL source identity")
        return metadata(r)
def download(kind,path):
    n=0;h=hashlib.sha256()
    with response(kind) as res,path.open("xb") as f:
        require(res.geturl()==URLS[kind],"DOL source identity")
        meta=metadata(res);declared=meta["bytes"]
        if declared is not None:require(0<declared<=MAX_DOWNLOAD[kind],"DOL compressed size bound")
        while chunk:=res.read(1024*1024):
            n+=len(chunk);require(n<=MAX_DOWNLOAD[kind],"DOL compressed size bound");h.update(chunk);f.write(chunk)
        require(n>0 and (declared is None or n==declared),"DOL transfer completeness")
    return {"url":URLS[kind],**meta,"bytes":n,"sha256":h.hexdigest()}
def identity(v):
    # Numeric field as documented. Do not repair unknown formatting or
    # collapse distinct source tokens via an integer cast.
    v=v.strip()
    return v if re.fullmatch(r"[0-9]{1,9}",v) and int(v)>0 else None
def date_year(v):
    s=v.strip()
    for fmt in ("%Y%m%d","%Y-%m-%d","%m/%d/%Y","%Y-%m-%d %H:%M:%S","%Y-%m-%dT%H:%M:%S"):
        try:
            d=datetime.strptime(s,fmt).date()
            return str(d.year) if date(1900,1,1)<=d<=datetime.now(timezone.utc).date() else "date_review"
        except ValueError:pass
    return "missing" if not s else "date_review"
def bucket(v,allowed):
    s=v.strip().upper()
    return s if s in allowed else "blank" if not s else "other"
def csv_members(z,kind):
    files=[i for i in z.infolist() if not i.is_dir()]
    require(0<len(files)<=512 and 0<sum(i.file_size for i in files)<=MAX_EXPANDED,"DOL ZIP expansion bound")
    names=[Path(i.filename).name for i in files]
    require(len(names)==len(set(names)) and all(n.lower().endswith(".csv") for n in names) and all(not i.flag_bits&1 for i in files),"DOL CSV member inventory")
    return sorted(files,key=lambda x:x.filename)
def walk(path,kind,consume):
    totals=Counter();members=[]
    with zipfile.ZipFile(path) as z:
        for info in csv_members(z,kind):
            n=0
            with z.open(info) as raw,io.TextIOWrapper(raw,encoding="utf-8-sig",newline="") as f:
                reader=csv.DictReader(f,strict=True);headers=reader.fieldnames or [];canonical=[x.upper() for x in headers]
                require(len(canonical)==len(set(canonical)) and REQUIRED[kind]<=set(canonical),"DOL required documented headers")
                for row in reader:
                    require(None not in row and all(v is not None for v in row.values()),"DOL CSV row shape")
                    n+=1;totals["screened"]+=1;require(totals["screened"]<=MAX_ROWS[kind],"DOL row bound")
                    consume(dict(zip(canonical,(row[k] for k in headers))))
            require(n>0 or info.file_size==0,"DOL member completeness")
            members.append({"name":Path(info.filename).name,"rows":n,"uncompressed_bytes":info.file_size,"crc32":format(info.CRC,"08x"),"headers":canonical})
    require(totals["screened"]>0 and totals["screened"]==sum(m["rows"] for m in members),"DOL member reconciliation")
    return totals["screened"],members
def inspect(path):
    counts=Counter();sectors=Counter();years=Counter();states=Counter();scopes=Counter();ids={}
    def consume(row):
        naics=row["NAICS_CODE"].strip()
        if not re.fullmatch(r"[0-9]{6}",naics) or naics=="000000":counts["missing_or_unrecognized_naics"]+=1;return
        sector=naics[:3]
        if sector not in SECTORS:counts["outside_sector62"]+=1;return
        k=identity(row["ACTIVITY_NR"])
        if k is None:counts["sector62_unresolved_activity_key"]+=1;return
        counts["sector62_valid_activity_rows"]+=1
        if k in ids:
            counts["sector62_repeated_activity_rows"]+=1
            require(ids[k]==sector,"conflicting healthcare activity classification")
        else:ids[k]=sector
        sectors[sector]+=1;years[date_year(row["OPEN_DATE"])]+=1
        states[bucket(row["SITE_STATE"],STATES)]+=1
        scopes[bucket(row["INSP_SCOPE"],{"A","B","C","D"})]+=1
    n,members=walk(path,"inspection",consume)
    require(n==sum(counts[k] for k in ("missing_or_unrecognized_naics","outside_sector62","sector62_unresolved_activity_key","sector62_valid_activity_rows")) and ids,"inspection row reconciliation")
    require(sum(sectors.values())==sum(years.values())==sum(states.values())==sum(scopes.values())==counts["sector62_valid_activity_rows"]==len(ids)+counts["sector62_repeated_activity_rows"],"inspection aggregate reconciliation")
    return ids,{"source_rows_screened":n,"members":members,"dispositions":dict(counts),"sector62_activity_keys":len(ids),"healthcare_621_623_activity_keys":sum(x!="624" for x in ids.values()),"sector62_source_rows_by_subsector":dict(sectors),"sector62_source_rows_by_open_year":dict(years),"sector62_source_rows_by_state":dict(states),"sector62_source_rows_by_scope_code":dict(scopes)}
def violations(path,ids):
    counts=Counter();flags=Counter();types=Counter();matched=set()
    def consume(row):
        k=identity(row["ACTIVITY_NR"])
        if k is None:counts["unrecognized_activity_key"]+=1;return
        if k not in ids:counts["outside_resolved_sector62_activity_keys"]+=1;return
        counts["sector62_activity_key_match"]+=1;matched.add(k)
        flag=bucket(row["DELETE_FLAG"],{"D","X"});flags[flag]+=1
        # Retain the literal domain; the publisher's deleted flag wording
        # and observed source spelling are not silently resolved.
        types[bucket(row["VIOL_TYPE"],{"S","W","R","O"})]+=1
        if not row["CITATION_ID"].strip():counts["matched_blank_citation_id_rows"]+=1
    n,members=walk(path,"violation",consume)
    require(n==sum(counts[k] for k in ("unrecognized_activity_key","outside_resolved_sector62_activity_keys","sector62_activity_key_match")),"violation row reconciliation")
    require(sum(flags.values())==sum(types.values())==counts["sector62_activity_key_match"] and matched<=set(ids),"violation link reconciliation")
    return {"source_rows_screened":n,"members":members,"dispositions":dict(counts),"matched_sector62_activity_keys":len(matched),"matched_rows_by_delete_flag_literal":dict(flags),"matched_rows_by_violation_type_literal":dict(types)}
def qualify(root):
    """Screen both exact publisher editions; leave only aggregate data in memory."""
    before={k:head(k) for k in URLS};meta={}
    for k in URLS:
        path=root/(k+".zip");meta[k]=download(k,path)
        require(all(meta[k][f]==v for f,v in before[k].items() if v is not None),"DOL source changed since HEAD")
        if k=="inspection":ids,ins=inspect(path)
        else:viol=violations(path,ids)
        require(sha(path)==meta[k]["sha256"],"DOL source mutated")
        path.unlink()
    require(all(head(k)==before[k] for k in URLS),"DOL edition changed during acquisition")
    # Combined source identity is a canonical manifest digest, not a raw ZIP hash.
    combined=hashlib.sha256(json.dumps({k:{"url":v["url"],"sha256":v["sha256"],"bytes":v["bytes"]} for k,v in meta.items()},sort_keys=True,separators=(",",":")).encode()).hexdigest()
    publisher={"kind":"multi_archive_publisher_manifest","sha256":combined,"documentation":DOC,"sources":meta,"retrieved_at":datetime.now(timezone.utc).isoformat()}
    summary={"aggregate_rows":1,"source_rows_screened":ins["source_rows_screened"]+viol["source_rows_screened"],"inspection":ins,"violation":viol,"site_or_event_rows_retained":0,"source_keys_retained":0,"scope":"DOL inspection and violation bulk editions, sector 62 code observations and exact activity-number matches. Different member dates may reflect different publisher cuts; counts are source rows, not unique facilities, current unresolved violations, or legal compliance judgments. NAICS is unavailable for older inspections; no SIC crosswalk or injury records. No raw identifiers or narratives retained.","public_promotion":False}
    return publisher,summary

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--receipt",type=Path,required=True)
    p.add_argument("--qualify-only",action="store_true",help="Validate both publisher archives without Azure, writing an aggregate-only local receipt")
    args=p.parse_args(argv)
    require(not args.receipt.exists(),"receipt exists")
    if args.qualify_only:
        with tempfile.TemporaryDirectory(prefix="osha-enforcement-coverage-") as d:
            publisher,summary=qualify(Path(d))
        rec={"status":"QUALIFIED_LOCAL_ONLY","source_sha256":publisher["sha256"],"publisher":publisher,
             "summary":summary,"azure_writes":0,"archive_readback_verified":False,"public_promotion":False}
        with args.receipt.open("xb") as f:f.write(a.encode(rec))
        print("OSHA_ENFORCEMENT_QUALIFIED_LOCAL_ONLY",json.dumps(rec,sort_keys=True),flush=True)
        return

    a.run_key(os.environ);store=storage.SourceAzure(os.environ)
    try:
        national=storage.national_manifest(store)
        with tempfile.TemporaryDirectory(prefix="osha-enforcement-coverage-") as d:
            root=Path(d);publisher,summary=qualify(root)
            rec=storage.existing(store,KEY,publisher["sha256"])
            if rec is None:
                out=root/"projection.sqlite3";write_aggregate(out,summary)
                audit={"publisher":publisher,"summary":summary,"projection_sha256":sha(out),"projection_bytes":out.stat().st_size,"reuse_review":"pending","public_promotion":False}
                rec=storage.publish(store,KEY,publisher,out,audit,root,national)
            require(rec["summary"]["aggregate_rows"]==1 and rec["summary"]["source_keys_retained"]==0,"aggregate receipt scope")
        with args.receipt.open("xb") as f:f.write(a.encode(rec))
        print("PRIVATE_OSHA_ENFORCEMENT_COVERAGE_COMPLETE",json.dumps(rec,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
