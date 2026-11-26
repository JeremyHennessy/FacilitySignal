"""Bounded NPPES V2 organization-only streaming qualification.

No individual names, personal identifiers, contacts, tax identifiers, addresses,
or endpoint values are retained. Source ZIP stays in a private temporary runner
directory; no extraction or raw/row-level artifacts. An NPI is not a physical
site, certification, active license or verified commercial opportunity.
"""
import argparse,csv,hashlib,io,json,re,shutil,sqlite3,tempfile,urllib.request,zipfile
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
from html.parser import HTMLParser
from pathlib import Path,PurePosixPath
from urllib.parse import urljoin,urlsplit
from build_combined import require

PAGE="https://download.cms.gov/nppes/NPI_Files.html"
LABELS={
    "weekly":"NPPES Data Dissemination V.2 - Weekly Update - 111626_112226",
    "monthly":"NPPES Data Dissemination V.2 (November 09, 2026)",
}
MAX_BYTES={"weekly":50_000_000,"monthly":1_500_000_000}
MAX_EXPANDED={"weekly":1_000_000_000,"monthly":30_000_000_000}
MAX_ROWS={"weekly":500000,"monthly":20000000}
REQUIRED=["NPI","Entity Type Code","Provider Organization Name (Legal Business Name)",
          "Provider Enumeration Date","Last Update Date","NPI Deactivation Date","NPI Reactivation Date",
          "Provider Business Practice Location Address State Name",
          "Provider Business Practice Location Address Country Code (If outside U.S.)",
          "Healthcare Provider Taxonomy Code_1","Healthcare Provider Primary Taxonomy Switch_1"]
PATTERNS={
    "main":r"npidata_pfile_[0-9]{8}-[0-9]{8}\.csv",
    "header":r"npidata_pfile_[0-9]{8}-[0-9]{8}_fileheader\.csv",
    "other_name":r"othername_pfile_[0-9]{8}-[0-9]{8}\.csv",
    "practice_location":r"pl_pfile_[0-9]{8}-[0-9]{8}\.csv",
    "endpoint":r"endpoint_pfile_[0-9]{8}-[0-9]{8}\.csv",
}
def allowed(url):
    p=urlsplit(url)
    require(p.scheme=="https" and p.hostname=="download.cms.gov" and p.port in (None,443)
            and not p.username and not p.password and not p.query and not p.fragment
            and p.path.lower().startswith("/nppes/"),"unexpected publisher URL")
    return url
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        allowed(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)
def response(url):
    req=urllib.request.Request(allowed(url),headers={"User-Agent":"FacilitySignal public institutional source qualification","Accept":"*/*"})
    return urllib.request.build_opener(Redirect()).open(req,timeout=120)
class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.href=None;self.parts=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=="a":self.href=dict(attrs).get("href");self.parts=[]
    def handle_data(self,data):
        if self.href is not None:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=="a" and self.href is not None:
            self.links.append((self.href," ".join("".join(self.parts).split())));self.href=None
def resolve(html,kind,*,publisher_label=None):
    p=Links();p.feed(html);p.close()
    urls={allowed(urljoin(PAGE,href)) for href,label in p.links if label==(publisher_label or LABELS[kind])}
    require(len(urls)==1,"exact V2 publisher release link absent or ambiguous")
    url=urls.pop();require(urlsplit(url).path.lower().endswith(".zip"),"release link not ZIP")
    return url
def download(path,kind,*,publisher_label=None):
    require(shutil.disk_usage(path.parent).free>=MAX_BYTES[kind]+1_000_000_000,"insufficient temporary disk")
    with response(PAGE) as res:
        page=res.read(5_000_001);require(0<len(page)<=5_000_000,"publisher index bound")
    url=resolve(page.decode("utf-8",errors="strict"),kind,publisher_label=publisher_label)
    h=hashlib.sha256();size=0
    with response(url) as res,path.open("xb") as out:
        final=allowed(res.geturl());require(urlsplit(final).path.lower().endswith(".zip"),"unexpected archive response")
        declared=res.headers.get("Content-Length")
        if declared is not None:require(declared.isdigit() and 0<int(declared)<=MAX_BYTES[kind],"declared archive bound")
        while chunk:=res.read(1024*1024):
            size+=len(chunk);require(size<=MAX_BYTES[kind],"archive download bound")
            h.update(chunk);out.write(chunk)
        if declared is not None:require(size==int(declared),"archive length mismatch")
        meta={"url":final,"bytes":size,"sha256":h.hexdigest(),"last_modified":res.headers.get("Last-Modified"),
              "etag":res.headers.get("ETag"),"retrieved_at":datetime.now(timezone.utc).isoformat()}
    require(zipfile.is_zipfile(path),"not ZIP")
    return meta
def members(z,kind):
    entries=[x for x in z.infolist() if not x.is_dir()]
    require(0<len(entries)<=30 and sum(x.file_size for x in entries)<=MAX_EXPANDED[kind],"archive expansion bound")
    found={}
    for x in entries:
        name=PurePosixPath(x.filename).name
        for key,pattern in PATTERNS.items():
            if re.fullmatch(pattern,name,re.I):
                require(key not in found and not x.flag_bits&1,"duplicate or encrypted member")
                found[key]=x
    require(set(found)==set(PATTERNS),"expected V2 archive member absent")
    return found
def npi_valid(s):
    if not re.fullmatch(r"[12][0-9]{9}",s):return False
    total=0
    for i,c in enumerate(reversed("80840"+s)):
        n=int(c)*(2 if i%2 else 1);total+=n-9 if n>9 else n
    return total%10==0
def date_state(s):
    v=s.strip()
    if not v:return "blank"
    if not re.fullmatch(r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}",v):return "unrecognized"
    try:datetime.strptime(v,"%m/%d/%Y")
    except ValueError:return "invalid"
    return "reported"
def present(s):return "present" if s.strip() else "blank"
def main_rows(reader,header,db,limit,*,organization_observer=None):
    require(0<len(header)<=500 and len(set(header))==len(header),"header uniqueness/bound")
    require(all(h in header for h in REQUIRED),"required organization header absent")
    m={h:header.index(h) for h in REQUIRED}
    tax=[i for i,h in enumerate(header) if re.fullmatch(r"Healthcare Provider Taxonomy Code_[0-9]+",h)]
    require(len(tax)==15,"taxonomy field count changed")
    types=Counter();counts=Counter();states={h:Counter() for h in ("legal_name","enumeration","updated","deactivation","reactivation","primary_taxonomy_switch","taxonomy_presence","practice_state_presence","practice_country_presence")}
    db.execute("CREATE TABLE organizations(npi TEXT PRIMARY KEY) WITHOUT ROWID")
    batch=[];total=0;duplicate=0
    def flush():
        nonlocal duplicate
        before=db.total_changes;db.executemany("INSERT OR IGNORE INTO organizations VALUES(?)",batch)
        duplicate+=len(batch)-(db.total_changes-before);batch.clear()
    for total,row in enumerate(reader,1):
        require(total<=limit,"main row bound")
        if len(row)!=len(header):types["malformed_width"]+=1;continue
        entity=row[m["Entity Type Code"]].strip()
        # Individual records are counted by class only. No identifier is read
        # from them or placed in any persistent/temporary projection.
        if entity=="1":types["individual_excluded"]+=1;continue
        if not entity:
            types["untyped_with_deactivation" if row[m["NPI Deactivation Date"]].strip() else "untyped_other"]+=1;continue
        if entity!="2":types["unrecognized_entity_type"]+=1;continue
        types["organization"]+=1
        npi=row[m["NPI"]].strip()
        if not npi_valid(npi):counts["invalid_organization_npi"]+=1;continue
        batch.append((npi,))
        if len(batch)>=10000:flush()
        counts["valid_organization_npi"]+=1
        def get(k):return row[m[k]]
        if organization_observer is not None:organization_observer(db,npi,total,get,tuple(row[i] for i in tax))
        states["legal_name"][present(get("Provider Organization Name (Legal Business Name)"))]+=1
        for key,field in (("enumeration","Provider Enumeration Date"),("updated","Last Update Date"),("deactivation","NPI Deactivation Date"),("reactivation","NPI Reactivation Date")):
            states[key][date_state(get(field))]+=1
        switch=get("Healthcare Provider Primary Taxonomy Switch_1").strip()
        states["primary_taxonomy_switch"][switch if switch in {"Y","N","X"} else "blank" if not switch else "unrecognized"]+=1
        states["taxonomy_presence"]["present" if any(row[i].strip() for i in tax) else "blank"]+=1
        states["practice_state_presence"][present(get("Provider Business Practice Location Address State Name"))]+=1
        states["practice_country_presence"][present(get("Provider Business Practice Location Address Country Code (If outside U.S.)"))]+=1
    if batch:flush()
    if organization_observer is not None and hasattr(organization_observer,'finish'):organization_observer.finish(db)
    db.commit();unique=db.execute("SELECT count(*) FROM organizations").fetchone()[0]
    require(total==sum(types.values()) and types["organization"]==sum(counts.values()),"entity reconciliation")
    require(unique+duplicate==counts["valid_organization_npi"] and all(sum(v.values())==counts["valid_organization_npi"] for v in states.values()),"organization reconciliation")
    require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite integrity")
    return {"input_rows":total,"columns":len(header),"entity_classes":dict(types),"organization_key_counts":dict(counts),
            "distinct_valid_organization_npis":unique,"duplicate_valid_organization_rows":duplicate,
            "organization_field_states":{k:dict(v) for k,v in states.items()}}
def ref_rows(reader,header,db,limit):
    require("NPI" in header and len(header)<=100 and len(set(header))==len(header),"reference header")
    idx=header.index("NPI");counts=Counter();total=0;matched=set()
    for total,row in enumerate(reader,1):
        require(total<=limit,"reference row bound")
        if len(row)!=len(header):counts["malformed_width"]+=1;continue
        npi=row[idx].strip()
        if not re.fullmatch(r"[0-9]{10}",npi):counts["invalid_key_shape"]+=1;continue
        if db.execute("SELECT 1 FROM organizations WHERE npi=?",(npi,)).fetchone():
            counts["type2_key_match"]+=1;matched.add(npi)
        else:counts["outside_qualified_type2_scope"]+=1
    require(total==sum(counts.values()),"reference reconciliation")
    return {"input_rows":total,"columns":len(header),"key_counts":dict(counts),"distinct_matched_type2_npis":len(matched),
            "limits":"Reference membership only; no address, alternative name or individual/endpoint value retained. Outside scope is not an orphan or invalid registration."}
def inspect(path,db_path,kind,*,organization_observer=None):
    csv.field_size_limit(1_000_000)
    with zipfile.ZipFile(path) as z,closing(sqlite3.connect(db_path)) as db:
        found=members(z,kind)
        # Stream each member; never extract the multi-GB CSV.
        with z.open(found["header"]) as raw,io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",errors="strict") as f:
            h=list(csv.reader(f,strict=True));require(len(h)==1,"header file shape")
        with z.open(found["main"]) as raw,io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",errors="strict") as f:
            reader=csv.reader(f,strict=True);header=next(reader,[])
            require(header==h[0],"separate header disagreement")
            result=main_rows(reader,header,db,MAX_ROWS[kind],organization_observer=organization_observer)
        refs={}
        for role in ("other_name","practice_location"):
            with z.open(found[role]) as raw,io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",errors="strict") as f:
                reader=csv.reader(f,strict=True);refs[role]=ref_rows(reader,next(reader,[]),db,MAX_ROWS[kind])
        result["reference_files"]=refs
        result["archive_members"]={role:{"uncompressed_bytes":x.file_size,"crc32":format(x.CRC,"08x"),"parsed":role!="endpoint"} for role,x in found.items()}
        result["endpoint_values_parsed"]=False
        return result
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--kind",choices=LABELS,required=True);p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    with tempfile.TemporaryDirectory(prefix="nppes-v2-") as d:
        root=Path(d);path=root/"source.zip";meta=download(path,a.kind)
        result=inspect(path,root/"organization-index.sqlite3",a.kind)
    result.update({"source_id":"FS-004","scope":a.kind,"publisher_label":LABELS[a.kind],"publisher":meta,
                   "retained_row_level_records":0,"reuse_review":"pending",
                   "limits":"NPPES registration-level structural qualification only. Weekly is incremental, not national baseline. Type 1 excluded; untyped deactivated rows not inferred as Type 2. Endpoint values not parsed. No site identity or license/compliance inference. No persistent projection."})
    with a.audit.open("x") as f:json.dump(result,f,indent=2);f.write("\n")
    print("NPPES_V2_AUDIT",json.dumps(result),flush=True)
    classes=result["entity_classes"];keys=result["organization_key_counts"]
    require(result["distinct_valid_organization_npis"]>0 and not any(classes.get(k,0) for k in ("malformed_width","unrecognized_entity_type")),"main structure exceptions")
    require(keys.get("invalid_organization_npi",0)==result["duplicate_valid_organization_rows"]==0,"organization identifier exceptions")
    require(all(not x["key_counts"].get("malformed_width") and not x["key_counts"].get("invalid_key_shape") for x in result["reference_files"].values()),"reference structural exceptions")
if __name__=="__main__":main()
