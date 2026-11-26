"""Bounded FY2024 HHA20 HCRIS relational source qualification.

Stream every CSV record, reconcile report identifiers and child coordinates.
Do not retain alphanumeric cell contents, provider details or individual values.
This is structural qualification, not worksheet semantics or unique facility count.
"""
import argparse,csv,hashlib,io,json,re,tempfile,urllib.request,zipfile
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from html.parser import HTMLParser
from pathlib import Path,PurePosixPath
from urllib.parse import urljoin,urlsplit
from build_combined import require

PAGE="https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/cost-reports-fiscal-year/hha20-fy-2024-data-files"
DOC="https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/home-health-agency-1728-2020-form"
MAX_BYTES=650_000_000
MAX_EXPANDED=4_000_000_000
MAX_ROWS=45_000_000
HOSTS={"www.cms.gov","cms.gov","downloads.cms.gov"}
def allowed(url):
    p=urlsplit(url)
    require(p.scheme=="https" and p.hostname in HOSTS and p.port in (None,443) and not p.username and not p.password and not p.fragment,"unexpected CMS URL")
    return url
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        allowed(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)
def request(url):
    return urllib.request.build_opener(Redirect()).open(urllib.request.Request(allowed(url),headers={"User-Agent":"FacilitySignal source qualification","Accept":"*/*"}),timeout=120)
class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.link=None;self.parts=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=="a":self.link=dict(attrs).get("href");self.parts=[]
    def handle_data(self,data):
        if self.link is not None:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=="a" and self.link is not None:
            self.links.append((self.link," ".join("".join(self.parts).split())));self.link=None
def resolve(html):
    p=Links();p.feed(html)
    urls=set()
    for href,label in p.links:
        if re.fullmatch(r"HHA(?:-?2020|20)\s+FY\s*2024\s+DATA\s+FILES(?:\s*\(ZIP\))?",label,re.I):
            url=allowed(urljoin(PAGE,href))
            require(urlsplit(url).path.casefold().endswith(".zip"),"FY link is not ZIP")
            urls.add(url)
    require(len(urls)==1,"missing or ambiguous FY2024 archive")
    return urls.pop()
def download(path):
    with request(PAGE) as res:
        page=res.read(5_000_001)
        require(0<len(page)<=5_000_000,"page bound")
    url=resolve(page.decode("utf-8",errors="strict"))
    h=hashlib.sha256();n=0
    with request(url) as res,path.open("xb") as f:
        final=allowed(res.geturl())
        require(urlsplit(final).path.casefold().endswith(".zip"),"final archive URL")
        for chunk in iter(lambda:res.read(1024*1024),b""):
            n+=len(chunk);require(n<=MAX_BYTES,"compressed download bound")
            h.update(chunk);f.write(chunk)
        meta={"url":final,"bytes":n,"sha256":h.hexdigest(),"last_modified":res.headers.get("Last-Modified"),"etag":res.headers.get("ETag"),"retrieved_at":datetime.now(timezone.utc).isoformat()}
    return meta
def members(z):
    files=[i for i in z.infolist() if not i.is_dir()]
    require(0<len(files)<=20 and sum(x.file_size for x in files)<=MAX_EXPANDED,"archive expansion bound")
    roles={}
    for info in files:
        # No extraction. Restrict recognized CSV names; record only roles/sizes.
        name=PurePosixPath(info.filename).name.casefold()
        if not name.endswith(".csv"):continue
        role="alpha" if "alph" in name else "numeric" if "nmrc" in name or "numeric" in name else "report" if "rpt" in name or "report" in name else None
        if role:
            require(role not in roles and not info.flag_bits&1,"ambiguous/encrypted source member")
            roles[role]=info
    require(set(roles)=={"report","numeric","alpha"},"missing expected relational files")
    return roles
def report_key(raw):
    v=raw.strip()
    return v if re.fullmatch(r"[0-9]{1,15}",v) else None
def count_report(reader):
    keys=set();width=Counter();bad=duplicate=rows=0
    for row in reader:
        rows+=1;require(rows<=100000,"report row bound")
        width[str(len(row))]+=1
        k=report_key(row[0]) if row else None
        if not k:bad+=1;continue
        if k in keys:duplicate+=1
        keys.add(k)
    require(rows>0 and rows==len(keys)+bad+duplicate,"report reconciliation")
    return keys,{"rows":rows,"width_counts":dict(width),"distinct_report_keys":len(keys),"invalid_report_key_rows":bad,"duplicate_report_key_rows":duplicate}
def cell_state(s):
    v=s.strip()
    if not v:return "blank"
    if not re.fullmatch(r"[+-]?(?:[0-9]{1,30}(?:\.[0-9]{0,12})?|\.[0-9]{1,12})",v):return "unrecognized"
    try:n=Decimal(v)
    except InvalidOperation:return "unrecognized"
    return "zero" if n==0 else "positive" if n>0 else "negative"
def coordinate_shape(v):
    if not v:return "blank"
    if len(v)>24:return "over_24"
    return "".join("9" if "0"<=c<="9" else "A" if "A"<=c<="Z" else "a" if "a"<=c<="z" else "S" if c.isspace() else "P" for c in v)

def count_child(reader,keys,role):
    rows=0;width=Counter();link=Counter();coord=Counter();values=Counter();covered=set();coords=set();exceptions={k:Counter() for k in ('worksheet','line','column')}
    for row in reader:
        rows+=1;require(rows<=MAX_ROWS,"child row bound")
        width[str(len(row))]+=1
        if len(row)!=5:
            link["wrong_width"]+=1;coord["wrong_width"]+=1;values["wrong_width"]+=1;continue
        k=report_key(row[0])
        if k is None:link["invalid_report_key"]+=1
        elif k in keys:link["report_present"]+=1;covered.add(k)
        else:link["orphan_report_key"]+=1
        # Source coordinates only, not interpreted worksheet names or expense measures.
        a,b,c=(v.strip() for v in row[1:4])
        if re.fullmatch(r"[A-Z0-9]{7}",a) and re.fullmatch(r"[0-9]{1,5}",b) and re.fullmatch(r"[0-9]{1,5}",c):
            coord["shape_valid"]+=1;coords.add((a,b,c));require(len(coords)<=500000,"coordinate bound")
        else:
            coord["shape_unrecognized"]+=1
            for k,v in zip(exceptions,(a,b,c)):
                exceptions[k][coordinate_shape(v)]+=1
        values[cell_state(row[4]) if role=="numeric" else ("present" if row[4].strip() else "blank")]+=1
    require(rows>0 and rows==sum(link.values())==sum(coord.values())==sum(values.values()),"child reconciliation")
    return {"rows":rows,"width_counts":dict(width),"report_key_link_counts":dict(link),"reports_with_cells":len(covered),
            "coordinate_shape_counts":dict(coord),"unrecognized_coordinate_component_shapes":{k:dict(v) for k,v in exceptions.items()},"distinct_valid_worksheet_coordinates":len(coords),"value_states":dict(values)}
def inspect(path):
    with zipfile.ZipFile(path) as z:
        roles=members(z);result={}
        # Source may use legacy encoding; Latin-1 is only used for byte-preserving
        # structural inspection. No names or free-text semantics are decoded.
        with z.open(roles["report"]) as raw,io.TextIOWrapper(raw,encoding="latin-1",newline="") as f:
            keys,result["report"]=count_report(csv.reader(f,strict=True))
        for role in ("numeric","alpha"):
            with z.open(roles[role]) as raw,io.TextIOWrapper(raw,encoding="latin-1",newline="") as f:
                result[role]=count_child(csv.reader(f,strict=True),keys,role)
        for role,info in roles.items():
            result[role]["uncompressed_bytes"]=info.file_size;result[role]["zip_crc32"]=format(info.CRC,"08x")
        return result
def main():
    p=argparse.ArgumentParser();p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    with tempfile.TemporaryDirectory(prefix="hcris-hha-") as d:
        path=Path(d)/"source.zip";meta=download(path)
        require(meta["sha256"]=="d3bf63b5d6293aa98f5a1cee096858c5d32d322f3cbe8471d9b6d410b37182d6","prior archive changed")
        result=inspect(path)
    out={"source_id":"FS-055","form":"CMS-1728-20","fiscal_year":2024,"publisher":meta,"landing":PAGE,"documentation":DOC,
         "tables":result,"retained_row_level_records":0,"reuse_review":"pending",
         "limits":"Structural streaming qualification only. No worksheet measure/unit crosswalk, report-status interpretation, unique facility count or durable projection. Numeric and alpha cells are not additional facility records. No provider identity, individual cell or alpha text retained."}
    with a.audit.open("x") as f:json.dump(out,f,indent=2);f.write("\n")
    print("HCRIS_HHA_COORDINATE_DIAGNOSTIC",json.dumps(out),flush=True)
    rpt=result["report"]
    require(rpt["invalid_report_key_rows"]==rpt["duplicate_report_key_rows"]==0 and len(rpt["width_counts"])==1,"report exceptions")
    for role in ("numeric","alpha"):
        child=result[role]
        require(child["report_key_link_counts"]=={"report_present":child["rows"]},"child linkage exceptions")
        require(child["coordinate_shape_counts"]=={"shape_valid":child["rows"]},"coordinate exceptions")
        require(not child["value_states"].get("unrecognized"),"numeric syntax exceptions")
if __name__=="__main__":main()
