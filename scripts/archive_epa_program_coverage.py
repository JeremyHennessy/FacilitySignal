"""Bounded RCRA and ICIS-NPDES Part 1 aggregate source qualification.

Stream official program tables; join reported healthcare NAICS to exact program
keys in memory. Retain only national aggregate counts and source metadata.
No facility identifiers, addresses, coordinates, permit details, violations,
inspection records or facility-specific program relationships are persisted.
"""
import argparse,csv,hashlib,io,json,os,re,tempfile,urllib.request,zipfile
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
import azure_national_archive as a
from build_combined import require,sha
from scripts import azure_source_archive as storage
from scripts.archive_environment_state import write_aggregate
BASE="https://echo.epa.gov/files/echodownloads/"
SECTORS={"621","622","623","624"}
SCOPES={
 "rcra":{"key":"epa-rcra-healthcare-aggregate","url":BASE+"rcra_downloads.zip","doc":"https://echo.epa.gov/tools/data-downloads/rcrainfo-download-summary","naics":"RCRA_NAICS.csv","facility":"RCRA_FACILITIES.csv","tables":{"RCRA_NAICS.csv":("ID_NUMBER","ACTIVITY_LOCATION","NAICS_CODE"),"RCRA_FACILITIES.csv":("ID_NUMBER","ACTIVITY_LOCATION"),"RCRA_EVALUATIONS.csv":("ID_NUMBER","ACTIVITY_LOCATION"),"RCRA_VIOLATIONS.csv":("ID_NUMBER","ACTIVITY_LOCATION"),"RCRA_ENFORCEMENTS.csv":("ID_NUMBER","ACTIVITY_LOCATION")}},
 "npdes":{"key":"epa-npdes-part1-healthcare-aggregate","url":BASE+"npdes_downloads.zip","doc":"https://echo.epa.gov/tools/data-downloads/icis-npdes-download-summary","naics":"NPDES_NAICS.csv","facility":"ICIS_FACILITIES.csv","tables":{"NPDES_NAICS.csv":("NPDES_ID","NAICS_CODE"),"ICIS_FACILITIES.csv":("NPDES_ID",),"ICIS_PERMITS.csv":("EXTERNAL_PERMIT_NMBR",),"NPDES_INSPECTIONS.csv":("NPDES_ID",),"NPDES_PS_VIOLATIONS.csv":("NPDES_ID",),"NPDES_CS_VIOLATIONS.csv":("NPDES_ID",),"NPDES_SE_VIOLATIONS.csv":("NPDES_ID",),"NPDES_FORMAL_ENFORCEMENT_ACTIONS.csv":("NPDES_ID",),"NPDES_INFORMAL_ENFORCEMENT_ACTIONS.csv":("NPDES_ID",)}}
}
MAX_DOWNLOAD=600_000_000
MAX_EXPANDED=12_000_000_000
MAX_ROWS=30_000_000
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError("unexpected publisher redirect")
def download(scope,path):
    url=scope["url"];require(url in {v["url"] for v in SCOPES.values()},"approved EPA URL")
    req=urllib.request.Request(url,headers={"User-Agent":"FacilitySignal aggregate source qualification","Accept-Encoding":"identity"})
    n=0;h=hashlib.sha256()
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=120) as res,path.open("xb") as f:
        require(res.geturl()==url,"publisher identity")
        length=res.headers.get("Content-Length")
        if length:require(0<int(length)<=MAX_DOWNLOAD,"download bound")
        while chunk:=res.read(1024*1024):
            n+=len(chunk);require(n<=MAX_DOWNLOAD,"download bound");h.update(chunk);f.write(chunk)
        require(n>0 and (not length or n==int(length)),"download completeness")
        return {"url":url,"documentation":scope["doc"],"bytes":n,"sha256":h.hexdigest(),"etag":res.headers.get("ETag"),"last_modified":res.headers.get("Last-Modified"),"retrieved_at":datetime.now(timezone.utc).isoformat()}
def members(z,scope):
    entries=[x for x in z.infolist() if not x.is_dir()]
    require(0<len(entries)<=40 and 0<sum(x.file_size for x in entries)<=MAX_EXPANDED,"ZIP bounds")
    by={}
    for x in entries:
        name=Path(x.filename).name.upper()
        if name in {k.upper() for k in scope["tables"]}:
            require(name not in by and not x.flag_bits&1,"duplicate/encrypted selected ZIP member")
            by[name]=x
    require(set(by)=={k.upper() for k in scope["tables"]},"selected ZIP member inventory")
    return {k:by[k.upper()] for k in scope["tables"]}
def key_for(program,row):
    if program=="rcra":
        ident=row["ID_NUMBER"].strip();loc=row["ACTIVITY_LOCATION"].strip()
        return (ident,loc) if re.fullmatch(r"[A-Z0-9]{4,12}",ident) and re.fullmatch(r"[A-Z]{2}",loc) else None
    ident=row.get("NPDES_ID",row.get("EXTERNAL_PERMIT_NMBR","")).strip()
    return ident if re.fullmatch(r"[A-Z0-9-]{1,30}",ident) else None
def rows(z,info,required):
    with z.open(info) as raw,io.TextIOWrapper(raw,encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f,strict=True);headers=reader.fieldnames or []
        require(len(headers)==len(set(headers)) and set(required)<=set(headers),"documented key header mismatch: "+Path(info.filename).name)
        for n,row in enumerate(reader,1):
            require(n<=MAX_ROWS and None not in row and all(v is not None for v in row.values()),"source row shape/bound")
            yield row
def qualify(program,path):
    scope=SCOPES[program];counts={};eligible=defaultdict(set);resolved=set()
    with zipfile.ZipFile(path) as z:
        ms=members(z,scope)
        naics=scope["naics"];stats=Counter()
        for row in rows(z,ms[naics],scope["tables"][naics]):
            stats["screened"]+=1;code=row["NAICS_CODE"].strip()
            if not re.fullmatch(r"[0-9]{6}",code):stats["unrecognized_or_missing_naics"]+=1;continue
            if code[:3] not in SECTORS:stats["outside_sector62"]+=1;continue
            key=key_for(program,row)
            if key is None:stats["sector62_unresolved_key"]+=1;continue
            stats["sector62_valid_key"]+=1;eligible[key].add(code[:3])
            require(len(eligible)<=2_000_000,"classification key bound")
        require(stats["screened"]>0 and stats["screened"]==sum(stats[k] for k in ("unrecognized_or_missing_naics","outside_sector62","sector62_unresolved_key","sector62_valid_key")) and eligible,"NAICS row reconciliation")
        counts[naics]=dict(stats)
        facility=scope["facility"];stats=Counter()
        for row in rows(z,ms[facility],scope["tables"][facility]):
            stats["screened"]+=1;key=key_for(program,row)
            if key is None:stats["unrecognized_or_missing_key"]+=1;continue
            if key in eligible:stats["sector62_key_match"]+=1;resolved.add(key)
            else:stats["outside_sector62_key_match"]+=1
        require(stats["screened"]>0 and stats["screened"]==sum(stats[k] for k in ("unrecognized_or_missing_key","sector62_key_match","outside_sector62_key_match")) and resolved<=set(eligible) and resolved,"facility row reconciliation")
        counts[facility]=dict(stats)
        for table in scope["tables"]:
            if table in (naics,facility):continue
            stats=Counter()
            for row in rows(z,ms[table],scope["tables"][table]):
                stats["screened"]+=1;key=key_for(program,row)
                if key is None:stats["unrecognized_or_missing_key"]+=1
                elif key in resolved:stats["resolved_sector62_key_match"]+=1
                elif key in eligible:stats["unresolved_sector62_key_match"]+=1
                else:stats["outside_sector62_key_match"]+=1
            require(stats["screened"]==sum(stats[k] for k in ("unrecognized_or_missing_key","resolved_sector62_key_match","unresolved_sector62_key_match","outside_sector62_key_match")),"child row reconciliation")
            counts[table]=dict(stats)
        health=sum(bool(eligible[k]&{"621","622","623"}) for k in resolved)
        return {"aggregate_rows":1,"source_rows_screened":sum(v["screened"] for v in counts.values()),"program":program,"selected_members":{k:{"rows":counts[k],"uncompressed_bytes":ms[k].file_size,"zip_crc32":format(ms[k].CRC,"08x")} for k in scope["tables"]},"distinct_sector62_program_keys":len(eligible),"resolved_sector62_program_keys":len(resolved),"unresolved_sector62_program_keys":len(eligible)-len(resolved),"resolved_healthcare_621_623_program_keys":health,"site_or_system_rows_retained":0,"event_rows_retained":0,"scope":"National aggregate structural coverage and exact reported industry/program key associations only. Counts represent source rows, not unique events, active compliance or unique physical facilities. RCRA history and NPDES Part 2 effluent/DMR are outside scope.","public_promotion":False}
def main():
    p=argparse.ArgumentParser();p.add_argument("--source",choices=SCOPES,required=True);p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ)
    scope=SCOPES[args.source];store=storage.SourceAzure(os.environ)
    try:
        national=storage.national_manifest(store)
        with tempfile.TemporaryDirectory(prefix="epa-program-coverage-") as d:
            root=Path(d);path=root/"source.zip";meta=download(scope,path)
            result=storage.existing(store,scope["key"],meta["sha256"])
            if result is None:
                summary=qualify(args.source,path);require(sha(path)==meta["sha256"],"source mutated");path.unlink()
                out=root/"projection.sqlite3";write_aggregate(out,summary)
                audit={"publisher":meta,"summary":summary,"projection_sha256":sha(out),"projection_bytes":out.stat().st_size,"reuse_review":"pending","public_promotion":False}
                result=storage.publish(store,scope["key"],meta,out,audit,root,national)
        require(result["summary"]["program"]==args.source and result["summary"]["site_or_system_rows_retained"]==result["summary"]["event_rows_retained"]==0,"aggregate receipt scope")
        with args.receipt.open("xb") as f:f.write(a.encode(result))
        print("PRIVATE_EPA_PROGRAM_COVERAGE_COMPLETE",args.source,json.dumps(result,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
