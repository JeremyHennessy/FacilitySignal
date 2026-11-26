"""Qualify official Minnesota equipment snapshots and Illinois licensed directory.

MN retains only state-wide structural aggregates; no asset identifiers, owner
names, site addresses, technical specifications or inspection records survive.
IL retains the institutional name/license/city/county/type/expiry literals, not
contact or address details. Preserve source ordinals, never infer current status.
"""
import argparse,csv,hashlib,io,json,os,re,sqlite3,tempfile,urllib.request,zipfile
from collections import Counter
from contextlib import closing
from datetime import datetime,date,timezone
from pathlib import Path
from urllib.parse import urlencode,urlsplit
import azure_national_archive as a
from build_combined import require,sha,check_integrity
from scripts import azure_source_archive as storage
from scripts.archive_environment_state import write_aggregate
MN="https://secure.doli.state.mn.us/ccld/data/"
IL="https://data.illinois.gov"
IL_ID="53nt-jwqq"
SCOPES={
 "mn-boiler":{"key":"mn-boiler-aggregate","url":MN+"bpvsnapshot_csv.zip","zip":True,"headers":"Asset_Number Asset_Type MNB_Number Serial_Number NB_Number Last_Inspection_Date Inspection_Type Expiration_Date Asset_SubType Asset_Use Fuel_Type Manufacturer Year_Built MAWP Heating_Surface Max_BTU_Input Milestone Business_Name Location_Address1 Location_Address2 Location_City Location_County Location_Zip Owner_Name Owner_Address1 Owner_Address2 Owner_City Owner_State Owner_Zip Legacy_Site_No Location_Record_ID".split(),"date_fields":["Last_Inspection_Date","Expiration_Date"]},
 "mn-elevator":{"key":"mn-elevator-aggregate","url":MN+"elvsnapshot.csv","zip":False,"headers":"Asset_Number Status ExpirationDate SiteAddr Location_City Location_Zip Building_Use BusinessName Owner_Name Owner_Address Owner_Cty Owner_State Owner_Zip Manufacturer Install_Year Elevator_Use Lift_Method Capacity Speed Floors".split(),"date_fields":["ExpirationDate"]}
}
IL_FIELDS=("facility_name","address","city","county","zip","phone","license_number","facility_type","exp_date")
MAX_BYTES=150_000_000
MAX_ROWS=2_000_000
HOSTS={"secure.doli.state.mn.us","data.illinois.gov"}
def allowed(url):
    p=urlsplit(url)
    require(p.scheme=="https" and p.hostname in HOSTS and not p.username and not p.password and p.port in (None,443) and not p.fragment,"publisher host")
    return url
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        require(urlsplit(allowed(newurl)).hostname==urlsplit(req.full_url).hostname,"unexpected source redirect")
        return super().redirect_request(req,fp,code,msg,headers,newurl)
def response(url,accept="application/json",method="GET"):
    req=urllib.request.Request(allowed(url),method=method,headers={"User-Agent":"FacilitySignal source qualification","Accept":accept,"Accept-Encoding":"identity"})
    return urllib.request.build_opener(Redirect()).open(req,timeout=90)
def head(url):
    with response(url,"*/*","HEAD") as r:
        return {"etag":r.headers.get("ETag"),"last_modified":r.headers.get("Last-Modified"),"bytes":int(r.headers["Content-Length"]) if r.headers.get("Content-Length") else None}
def download(url,path):
    h=hashlib.sha256();n=0
    with response(url,"*/*") as r,path.open("xb") as f:
        length=r.headers.get("Content-Length")
        if length:require(0<int(length)<=MAX_BYTES,"state compressed size bound")
        while chunk:=r.read(1024*1024):
            n+=len(chunk);require(n<=MAX_BYTES,"state transfer bound");h.update(chunk);f.write(chunk)
        require(n>0 and (not length or n==int(length)),"state transfer completeness")
        return {"url":url,"final_url":r.geturl(),"bytes":n,"sha256":h.hexdigest(),"etag":r.headers.get("ETag"),"last_modified":r.headers.get("Last-Modified")}
def date_state(raw):
    s=raw.strip()
    if not s:return "blank"
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%m/%d/%Y %H:%M:%S","%Y-%m-%dT%H:%M:%S.%f","%Y-%m-%dT%H:%M:%S","%m/%d/%Y %I:%M:%S %p"):
        try:
            d=datetime.strptime(s,fmt).date()
            return "valid_calendar_date" if 1900<=d.year<=2200 else "date_review"
        except ValueError:pass
    return "date_review"
def mn_project(f,scope):
    reader=csv.DictReader(f,strict=True);require(reader.fieldnames==scope["headers"],"Minnesota exact reviewed header")
    fields=Counter();dates={k:Counter() for k in scope["date_fields"]};keys=set();counts=Counter();n=0
    for row in reader:
        n+=1;require(n<=MAX_ROWS and None not in row and all(v is not None for v in row.values()),"Minnesota CSV row width/bound")
        require(all(not any(ord(c)<32 and c not in "\r\n\t" or 127<=ord(c)<=159 for c in v) for v in row.values()),"Minnesota decoder control-character review")
        for k,v in row.items():fields[k]+=bool(v.strip())
        for k in dates:dates[k][date_state(row[k])]+=1
        token=row["Asset_Number"].strip()
        if not token:counts["blank_asset_number"]+=1
        elif len(token)>100:counts["asset_number_format_review"]+=1
        elif token in keys:counts["repeated_asset_number"]+=1
        else:keys.add(token);counts["distinct_asset_number"]+=1
    require(n>0 and n==sum(counts.values()) and all(sum(c.values())==n for c in dates.values()) and all(v<=n for v in fields.values()),"Minnesota row reconciliation")
    require(len(keys)==counts["distinct_asset_number"],"asset-number aggregate")
    return {"aggregate_rows":1,"source_rows_screened":n,"columns":len(scope["headers"]),"field_nonblank_counts":dict(fields),"asset_number_states":dict(counts),"date_value_states":{k:dict(v) for k,v in dates.items()},"site_or_equipment_rows_retained":0,"source_identifiers_retained":0,"encoding":"cp1252 (strict structural decoder; publisher encoding declaration not verified)","scope":"State equipment source rows, not healthcare-specific matches, unique equipment census, current operating condition or inspection compliance. No owner, site, asset or equipment detail retained.","public_promotion":False}
def minnesota(kind,root):
    scope=SCOPES[kind];path=root/"source.download";meta=download(scope["url"],path)
    require(meta["sha256"]==sha(path),"Minnesota source bytes")
    if scope["zip"]:
        with zipfile.ZipFile(path) as z:
            members=[m for m in z.infolist() if not m.is_dir()]
            require(len(members)==1 and members[0].file_size<=MAX_BYTES and re.fullmatch(r"BPV_SNAP_[0-9]{2}_[0-9]{2}_[0-9]{4}\.csv",Path(members[0].filename).name,re.I) and not members[0].flag_bits&1,"Minnesota boiler member scope")
            m=members[0]
            with z.open(m) as raw,io.TextIOWrapper(raw,encoding="cp1252",errors="strict",newline="") as f:summary=mn_project(f,scope)
            summary["member"]={"name":Path(m.filename).name,"crc32":format(m.CRC,"08x"),"bytes":m.file_size}
    else:
        with path.open(encoding="cp1252",errors="strict",newline="") as f:summary=mn_project(f,scope)
    require(sha(path)==meta["sha256"],"Minnesota source mutated")
    observed=head(scope["url"])
    require(any(meta[k] is not None for k in ("etag","last_modified")) and all(observed[k]==meta[k] for k in ("etag","last_modified","bytes") if observed[k] is not None),"Minnesota publisher metadata changed")
    out=root/"projection.sqlite3";write_aggregate(out,summary);path.unlink()
    return meta,summary,out
def get_json(url):
    with response(url) as r:
        raw=r.read(10_000_001);require(0<len(raw)<=10_000_000,"Illinois JSON bound")
    return json.loads(raw),raw
def il_metadata():
    doc,_=get_json(IL+"/api/views/"+IL_ID+".json")
    require(doc["id"]==IL_ID and doc["name"]=="IDPH Hospital Directory","Illinois directory identity")
    fields=[(c["fieldName"],c["dataTypeName"]) for c in doc["columns"] if not c["fieldName"].startswith(":")]
    require([x[0] for x in fields]==list(IL_FIELDS) and all(x[1]=="text" for x in fields[:-1]) and fields[-1][1]=="calendar_date","Illinois reviewed schema")
    c,_=get_json(IL+"/resource/"+IL_ID+".json?"+urlencode({"$select":"count(*) AS n"}))
    require(len(c)==1,"Illinois independent count envelope");n=int(c[0]["n"]);require(0<n<=1000,"Illinois count bound")
    return {"dataset_id":IL_ID,"title":doc["name"],"rows_updated_at":doc.get("rowsUpdatedAt"),"fields":[list(x) for x in fields],"count":n,"url":IL+"/resource/"+IL_ID+".json"}
def il_rows(meta):
    url=meta["url"]+"?"+urlencode({"$limit":1000,"$order":":id"})
    rows,raw=get_json(url);require(isinstance(rows,list) and len(rows)==meta["count"],"Illinois independent count reconciliation")
    return rows,hashlib.sha256(raw).hexdigest()
def literal(row,k,required=False):
    s=row.get(k)
    require(s is None or isinstance(s,str) and len(s)<=300 and not any(ord(c)<32 for c in s),"Illinois source field")
    s=s.strip() if s else None
    if required:require(bool(s),"Illinois required institutional identity")
    return s or None
def il_project(rows,out):
    counts=Counter();licenses=set()
    with closing(sqlite3.connect(out)) as db:
        db.execute("CREATE TABLE institutional_directory(source_ordinal INTEGER PRIMARY KEY,license_number TEXT,name TEXT NOT NULL,city TEXT,county TEXT,facility_type TEXT,expiry_source_text TEXT,expiry_value_state TEXT NOT NULL)")
        for ordinal,row in enumerate(rows,1):
            require(isinstance(row,dict) and set(row)<=set(IL_FIELDS),"Illinois source row schema")
            lic=literal(row,"license_number");name=literal(row,"facility_name",True);expiry=literal(row,"exp_date");state=date_state(expiry or "")
            if not lic:counts["blank_license"]+=1
            elif lic in licenses:counts["repeated_license"]+=1
            else:licenses.add(lic);counts["distinct_license"]+=1
            counts["expiry_"+state]+=1
            db.execute("INSERT INTO institutional_directory VALUES(?,?,?,?,?,?,?,?)",(ordinal,lic,name,literal(row,"city"),literal(row,"county"),literal(row,"facility_type"),expiry,state))
        db.commit();check_integrity(db)
        require(db.execute("SELECT count(*) FROM institutional_directory").fetchone()[0]==len(rows)>0 and sum(counts[k] for k in ("blank_license","repeated_license","distinct_license"))==len(rows),"Illinois retained row reconciliation")
    return {"stored_rows":len(rows),"input_rows":len(rows),"license_and_expiry_states":dict(counts),"contact_street_coordinates_retained":0,"scope":"IDPH Hospital Directory source observations, not the Hospital Report Card and not a verified active-status or unique site determination. Exact literal license text and expiry values; no automatic CCN join.","public_promotion":False}
def illinois(root):
    meta=il_metadata();rows,digest=il_rows(meta);again,d2=il_rows(meta)
    require(rows==again and digest==d2 and il_metadata()==meta,"Illinois edition changed")
    out=root/"projection.sqlite3";summary=il_project(rows,out)
    return {**meta,"kind":"ordered_publisher_response","sha256":digest},summary,out
def main():
    p=argparse.ArgumentParser();p.add_argument("--source",choices=(*SCOPES,"il-directory"),required=True);p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ);store=storage.SourceAzure(os.environ)
    try:
        national=storage.national_manifest(store)
        with tempfile.TemporaryDirectory(prefix="state-source-") as d:
            root=Path(d)
            if args.source=="il-directory":meta,summary,out=illinois(root);key="il-idph-hospital-directory"
            else:meta,summary,out=minnesota(args.source,root);key=SCOPES[args.source]["key"]
            receipt=storage.existing(store,key,meta["sha256"])
            if receipt is None:
                audit={"publisher":meta,"summary":summary,"projection_sha256":sha(out),"projection_bytes":out.stat().st_size,"reuse_review":"pending","public_promotion":False}
                receipt=storage.publish(store,key,meta,out,audit,root,national)
        with args.receipt.open("xb") as f:f.write(a.encode(receipt))
        print("PRIVATE_STATE_EQUIPMENT_DIRECTORY_COMPLETE",args.source,json.dumps(receipt,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
