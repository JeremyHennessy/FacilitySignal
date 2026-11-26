"""Bounded environmental and state institutional source expansion.

Water and equipment sources are aggregate-only; no facility-linked asset,
water-system, inspection vulnerability, contact or personal record retained.
Illinois report-card institutional directories retain only public identity fields.
"""
import argparse,csv,hashlib,io,json,os,re,sqlite3,tempfile,urllib.request
from collections import Counter
from contextlib import closing
from datetime import date,datetime,timezone
from pathlib import Path
from urllib.parse import urlencode,urlsplit
import azure_national_archive as a
from scripts import azure_source_archive as storage,qualify_epa_sdwa as water,audit_epa_medical_area as area
from build_combined import require,sha,check_integrity
IL="https://healthcarereportcard.illinois.gov"
WA="https://data.wa.gov"
WA_ID="eitf-fmad"
KEYS={"water":"epa-sdwa-aggregate","wa-xray":"wa-xray-aggregate","il-hospitals":"il-reportcard-hospitals","il-ascs":"il-reportcard-ascs"}

def allowed(url):
    p=urlsplit(url)
    require(p.scheme=="https" and p.netloc in {"healthcarereportcard.illinois.gov","data.wa.gov"} and not p.fragment,"unexpected state source host")
    return url
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        allowed(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)
def request(url,accept):
    req=urllib.request.Request(allowed(url),headers={"Accept":accept,"User-Agent":"FacilitySignal source qualification"})
    return urllib.request.build_opener(Redirect()).open(req,timeout=90)
def get_json(url):
    with request(url,"application/json") as res:
        b=res.read(10_000_001);require(0<len(b)<=10_000_000,"state JSON bound")
    return json.loads(b),b

def wa_metadata():
    meta,_=get_json(WA+"/api/views/"+WA_ID+".json")
    require(meta["id"]==WA_ID and " ".join(meta["name"].casefold().split())=="x-ray facility list","WA dataset identity")
    fields=[x["name"] for x in meta["columns"] if not str(x.get("fieldName","")).startswith(":")]
    require(0<len(fields)<=100 and len(fields)==len(set(fields)),"WA schema metadata")
    count,_=get_json(WA+"/resource/"+WA_ID+".json?"+urlencode({"$select":"count(*) AS n"}))
    n=int(count[0]["n"]);require(len(count)==1 and 0<n<=300000,"WA count")
    return {"dataset_id":WA_ID,"title":meta["name"],"rows_updated_at":meta.get("rowsUpdatedAt"),"view_last_modified":meta.get("viewLastModified"),"fields":fields,"count":n,"license":meta.get("licenseId"),"url":WA+"/api/views/"+WA_ID+"/rows.csv?accessType=DOWNLOAD"}

def write_aggregate(out,summary):
    with closing(sqlite3.connect(out)) as db:
        db.execute("CREATE TABLE aggregate_evidence(id INTEGER PRIMARY KEY CHECK(id=1),summary_json TEXT NOT NULL)")
        db.execute("INSERT INTO aggregate_evidence VALUES(1,?)",(json.dumps(summary,sort_keys=True),));db.commit();check_integrity(db)

def washington(root):
    m=wa_metadata();path=root/"source.csv";h=hashlib.sha256();n=0
    with request(m["url"],"text/csv") as res,path.open("xb") as f:
        while chunk:=res.read(1024*1024):
            n+=len(chunk);require(n<=80_000_000,"WA file bound");h.update(chunk);f.write(chunk)
    require(n>0 and wa_metadata()==m and sha(path)==h.hexdigest(),"WA source metadata or bytes changed")
    with path.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.reader(f,strict=True);header=next(reader)
        require(len(header)==len(set(header)) and set(header)==set(m["fields"]),"WA CSV schema mismatch")
        presence=Counter();count=0
        for row in reader:
            count+=1;require(count<=m["count"] and len(row)==len(header),"WA CSV shape")
            for k,v in zip(header,row):presence[k]+=bool(v.strip())
    require(count==m["count"],"WA count mismatch")
    summary={"source_rows_screened":count,"aggregate_rows":1,"columns":len(header),"field_nonblank_counts":dict(presence),"site_or_equipment_rows_retained":0,"scope":"State X-ray registration source coverage only; no equipment quantity or inspection status inferred.","public_promotion":False}
    out=root/"projection.sqlite3";write_aggregate(out,summary)
    return {**m,"sha256":h.hexdigest(),"bytes":n},summary,out

def epa(root):
    path=root/"source.zip";meta=water.download(path)
    require(meta["sha256"]==area.PIN and sha(path)==area.PIN,"EPA source differs from qualified release")
    result=area.audit(path)
    require(result["source_rows"]==434757 and result["area_counts"]["exact_code_and_description"]==1712,"EPA prior audit totals")
    require(sha(path)==area.PIN,"EPA source mutated")
    summary={"source_rows_screened":result["source_rows"],"aggregate_rows":1,"service_area_counts":result["area_counts"],"medical_identifier_format_counts":{k:v.get("exact_code_and_description",0) for k,v in result["area_by_identifier_state"].items()},"site_or_system_rows_retained":0,"scope":"Aggregate medical service-area code evidence only. Not a healthcare-site linkage, water system control or compliance conclusion.","public_promotion":False}
    out=root/"projection.sqlite3";write_aggregate(out,summary)
    return meta,summary,out

def page_rows(doc,page):
    require(isinstance(doc,dict) and isinstance(doc.get("data"),list),"IL documented resource list envelope")
    meta=doc.get("meta",doc)
    require(isinstance(meta,dict),"IL pagination metadata")
    current,last,total=(meta.get(k) for k in ("current_page","last_page","total"))
    require(type(current) is type(last) is type(total) is int and current==page and 0<last<=30 and 0<total<=3000,"IL pagination scope")
    rows=doc["data"];require(0<len(rows)<=100 and (page==last or len(rows)==100),"IL page length")
    return rows,last,total

def il_records(kind,get=get_json):
    rows=[];page=1;hashes=[];first=None;total=None;last=None
    while True:
        doc,raw=get(IL+"/api/"+kind+"?"+urlencode({"per_page":100,"page":page}))
        r,pages,count=page_rows(doc,page)
        if first is None:first=hashlib.sha256(raw).hexdigest();last=pages;total=count
        require(last==pages and total==count,"IL pagination changed")
        hashes.append(hashlib.sha256(raw).hexdigest());rows.extend(r)
        if page==last:break
        page+=1
    require(len(rows)==total,"IL total count")
    check,_=get(IL+"/api/"+kind+"?"+urlencode({"per_page":100,"page":1}))
    cr,cp,ct=page_rows(check,1)
    require(cr==rows[:len(cr)] and cp==last and ct==total,"IL first page changed")
    return rows,hashes

def identifier(value,kind="entity"):
    if value is None or value=="":return None
    s=str(value)
    patterns={"entity":r"[0-9]{1,20}","license":r"(?:[0-9]{1,20}|[0-9]{4}-[0-9]|[0-9]{2}-[0-9]{4})","mpn":r"(?:[0-9]{1,20}|[0-9]{5}[A-Za-z])"}
    require(kind in patterns and re.fullmatch(patterns[kind],s) is not None,"IL identifier shape")
    return s
def field(value):
    if value is None:return None
    require(isinstance(value,str) and len(value)<=300 and "\x00" not in value,"IL field shape")
    return value.strip() or None
def illinois(kind,root):
    records,hashes=il_records(kind);required={"entity_id","local_id","mpn_id","name","city","county_name","closed_date"};out=root/"projection.sqlite3"
    with closing(sqlite3.connect(out)) as db:
        db.execute("CREATE TABLE institutional_directory(entity_id TEXT PRIMARY KEY,license_id TEXT,mpn_source_text TEXT,name TEXT NOT NULL,city TEXT,county TEXT,reported_closed_date TEXT) WITHOUT ROWID")
        count=Counter();keys=[]
        for row in records:
            require(isinstance(row,dict) and required<=set(row),"IL source fields")
            eid=identifier(row["entity_id"]);lic=identifier(row["local_id"],"license");mpn=identifier(row["mpn_id"],"mpn");name=field(row["name"])
            closed=field(row["closed_date"])
            if closed:date.fromisoformat(closed)
            require(eid is not None and name is not None,"IL institutional identity")
            db.execute("INSERT INTO institutional_directory VALUES(?,?,?,?,?,?,?)",(eid,lic,mpn,name,field(row["city"]),field(row["county_name"]),closed));count["reported_closed" if closed else "no_reported_closure"]+=1
        db.commit();check_integrity(db)
        require(db.execute("SELECT count(*) FROM institutional_directory").fetchone()[0]==len(records)==sum(count.values()),"IL source count")
        summary={"stored_rows":len(records),"input_rows":len(records),"closure_date_states":dict(count),"contact_street_coordinates_retained":0,"source_scope":"Illinois Hospital Report Card "+kind+" institutional directory; source MPN is not normalized to CCN.","public_promotion":False}
    # Hash the exact ordered response page SHA-256s, not a purported publisher file hash.
    meta={"url":IL+"/api/"+kind,"documentation":IL+"/api/docs/"+kind,"page_sha256":hashes,"kind":"paginated_publisher_observation","sha256":hashlib.sha256(a.encode({"source":kind,"page_sha256":hashes})).hexdigest()}
    return meta,summary,out

def main():
    p=argparse.ArgumentParser();p.add_argument("--source",choices=KEYS,required=True);p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ);store=storage.SourceAzure(os.environ)
    try:
        national=storage.national_manifest(store)
        with tempfile.TemporaryDirectory(prefix="environment-state-source-") as d:
            root=Path(d)
            if args.source=="water":meta,summary,out=epa(root)
            elif args.source=="wa-xray":meta,summary,out=washington(root)
            else:meta,summary,out=illinois(args.source.removeprefix("il-"),root)
            key=KEYS[args.source];receipt=storage.existing(store,key,meta["sha256"])
            if receipt is None:
                audit={"publisher":meta,"summary":summary,"projection_sha256":sha(out),"projection_bytes":out.stat().st_size,"reuse_review":"pending","public_promotion":False}
                receipt=storage.publish(store,key,meta,out,audit,root,national)
        with args.receipt.open("xb") as f:f.write(a.encode(receipt))
        print("PRIVATE_ENVIRONMENT_STATE_COMPLETE",args.source,json.dumps(receipt,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
