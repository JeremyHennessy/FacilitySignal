"""Read-only publisher schema probes; never emit source row values."""
import csv,io,json,tempfile,urllib.request,urllib.error,zipfile,hashlib
from pathlib import Path
from urllib.parse import urlsplit
from build_combined import require
SOURCES={
 "mn-boiler":{"url":"https://secure.doli.state.mn.us/ccld/data/bpvsnapshot_csv.zip","zip":True},
 "mn-elevator":{"url":"https://secure.doli.state.mn.us/ccld/data/elvsnapshot.csv","zip":False},
 "il-directory-new":{"url":"https://data.illinois.gov/api/views/53nt-jwqq.json","json":True},
 "il-directory-legacy":{"url":"https://data.illinois.gov/api/views/wsms-teqm.json","json":True}
}
MAX_BYTES=150_000_000
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        require(urlsplit(newurl).scheme=="https" and urlsplit(newurl).hostname==urlsplit(req.full_url).hostname,"publisher host redirect")
        return super().redirect_request(req,fp,code,msg,headers,newurl)
def csv_probe(f):
    r=csv.reader(f,strict=True);header=next(r)
    require(0<len(header)<=200 and all(len(v)<=200 for v in header) and len(set(header))==len(header),"CSV header scope")
    widths={};n=0
    for row in r:
        n+=1;require(n<=2_000_000,"row bound")
        widths[str(len(row))]=widths.get(str(len(row)),0)+1
    return {"headers":header,"rows":n,"row_width_counts":widths}
def probe(name,scope,root):
    url=scope["url"];p=root/(name+".download")
    req=urllib.request.Request(url,headers={"User-Agent":"FacilitySignal publisher schema diagnostic","Accept-Encoding":"identity"})
    with urllib.request.build_opener(Redirect()).open(req,timeout=60) as r,p.open("xb") as out:
        declared=r.headers.get("Content-Length")
        if declared:require(0<int(declared)<=MAX_BYTES,"source transfer bound")
        h=hashlib.sha256();n=0
        while chunk:=r.read(1024*1024):
            n+=len(chunk);require(n<=MAX_BYTES,"source transfer bound");h.update(chunk);out.write(chunk)
        require(n>0 and (not declared or n==int(declared)),"source transfer completeness")
        meta={"url":url,"final_url":r.geturl(),"bytes":n,"sha256":h.hexdigest(),"etag":r.headers.get("ETag"),"last_modified":r.headers.get("Last-Modified"),"content_type":r.headers.get("Content-Type")}
    if scope.get("json"):
        j=json.loads(p.read_bytes());cols=j.get("columns",[])
        require(j.get("id") in ("53nt-jwqq","wsms-teqm") and cols,"Socrata metadata identity")
        return {"status":"METADATA_PASS","publisher":meta,"id":j["id"],"name":j.get("name"),"rowsUpdatedAt":j.get("rowsUpdatedAt"),"columns":[{"field":x.get("fieldName"),"label":x.get("name"),"type":x.get("dataTypeName")} for x in cols]}
    if scope.get("zip"):
        with zipfile.ZipFile(p) as z:
            members=[m for m in z.infolist() if not m.is_dir()]
            require(len(members)==1 and members[0].file_size<=MAX_BYTES and Path(members[0].filename).suffix.casefold()==".csv","ZIP member scope")
            m=members[0]
            with z.open(m) as raw,io.TextIOWrapper(raw,encoding="utf-8-sig",newline="") as f:result=csv_probe(f)
            result.update({"member":Path(m.filename).name,"crc32":format(m.CRC,"08x")})
    else:
        with p.open(encoding="utf-8-sig",newline="") as f:result=csv_probe(f)
    return {"status":"SCHEMA_PASS","publisher":meta,"result":result}
with tempfile.TemporaryDirectory(prefix="state-source-schema-") as d:
    root=Path(d)
    for name,scope in SOURCES.items():
        try:result=probe(name,scope,root)
        except urllib.error.HTTPError as e:result={"status":"ACCESS_BLOCKED","http_status":e.code}
        except Exception as e:result={"status":"REVIEW_REQUIRED","error_type":type(e).__name__}
        print("STATE_SOURCE_SCHEMA",name,json.dumps(result,sort_keys=True),flush=True)
