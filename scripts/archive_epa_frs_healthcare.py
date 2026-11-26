"""Stream the ECHO FRS subset and retain only healthcare-sector coverage aggregates.

Publisher file grains remain separate: facility, NAICS association, program link.
No facility name, address, coordinate, registry ID, permit ID, equipment details,
compliance status or row-level relationship is retained or emitted. Temporary
SQLite holds keys only for exact joins and is removed after qualification.
"""
import argparse,csv,hashlib,io,json,os,re,sqlite3,tempfile,urllib.request,zipfile
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
import azure_national_archive as a
from build_combined import require,sha,check_integrity
from scripts import azure_source_archive as storage
from scripts.archive_environment_state import write_aggregate

URL="https://echo.epa.gov/files/echodownloads/frs_downloads.zip"
DOC="https://echo.epa.gov/tools/data-downloads/frs-download-summary"
KEY="epa-frs-healthcare-aggregate"
MAX_DOWNLOAD=500_000_000
MAX_EXPANDED=4_500_000_000
MAX_ROWS=25_000_000
REQUIRED={"FRS_FACILITIES.csv":{"REGISTRY_ID","FAC_STATE"},"FRS_NAICS_CODES.csv":{"REGISTRY_ID","NAICS_CODE","PGM_SYS_ACRNM","PGM_SYS_ID"},"FRS_PROGRAM_LINKS.csv":{"REGISTRY_ID","PGM_SYS_ACRNM","PGM_SYS_ID"}}
SECTORS={"621":"ambulatory_healthcare_services","622":"hospitals","623":"nursing_and_residential_care","624":"social_assistance"}
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        require(newurl==URL,"unexpected FRS redirect")
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def download(path):
    req=urllib.request.Request(URL,headers={"User-Agent":"FacilitySignal official FRS aggregate qualification","Accept-Encoding":"identity"})
    digest=hashlib.sha256();n=0
    with urllib.request.build_opener(Redirect()).open(req,timeout=120) as res,path.open("xb") as out:
        require(res.geturl()==URL,"FRS source identity")
        length=res.headers.get("Content-Length")
        if length:require(0<int(length)<=MAX_DOWNLOAD,"FRS compressed size bound")
        while chunk:=res.read(1024*1024):
            n+=len(chunk);require(n<=MAX_DOWNLOAD,"FRS compressed size bound");digest.update(chunk);out.write(chunk)
        require(n>0 and (not length or n==int(length)),"FRS transfer completeness")
        return {"url":URL,"documentation":DOC,"title":"ECHO FRS facilities and linkages subset","bytes":n,"sha256":digest.hexdigest(),"etag":res.headers.get("ETag"),"last_modified":res.headers.get("Last-Modified"),"retrieved_at":datetime.now(timezone.utc).isoformat()}

def members(z):
    entries=[i for i in z.infolist() if not i.is_dir()]
    require(0<len(entries)<=20 and 0<sum(i.file_size for i in entries)<=MAX_EXPANDED,"FRS archive bounds")
    by_name={}
    for m in entries:
        name=Path(m.filename).name.upper()
        if name in {k.upper() for k in REQUIRED}:
            require(name not in by_name and not m.flag_bits&1,"duplicate or encrypted FRS member")
            by_name[name]=m
    require(set(by_name)=={k.upper() for k in REQUIRED},"FRS selected member scope")
    return {k:by_name[k.upper()] for k in REQUIRED}

def reader(z,info,required):
    raw=z.open(info);f=io.TextIOWrapper(raw,encoding="utf-8-sig",newline="")
    r=csv.DictReader(f,strict=True);header=r.fieldnames or []
    if len(header)!=len(set(header)) or not required<=set(header):
        f.close();raise ValueError("FRS required documented header mismatch")
    return f,r

def rows(r):
    for n,row in enumerate(r,1):
        require(n<=MAX_ROWS and None not in row and all(v is not None for v in row.values()),"FRS row bounds")
        yield row

def registry_id(v):
    # Exact literal bounded registry identifier, not a guessed replacement.
    return v if re.fullmatch(r"[0-9]{12}",v) else None

def code(v):
    v=v.strip()
    return v if re.fullmatch(r"[A-Z0-9 _./-]{1,60}",v) else None

def qualify(path,scratch):
    with zipfile.ZipFile(path) as z,closing(sqlite3.connect(scratch)) as db:
        ms=members(z)
        db.executescript("""
        CREATE TABLE health_codes(id TEXT NOT NULL,sector TEXT NOT NULL,PRIMARY KEY(id,sector)) WITHOUT ROWID;
        CREATE TABLE health_sites(id TEXT PRIMARY KEY,state TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE health_programs(id TEXT NOT NULL,program TEXT NOT NULL,PRIMARY KEY(id,program)) WITHOUT ROWID;
        CREATE TABLE all_facilities(id TEXT PRIMARY KEY) WITHOUT ROWID;
        """)
        counters={k:Counter() for k in REQUIRED};naics=counters["FRS_NAICS_CODES.csv"]
        f,r=reader(z,ms["FRS_NAICS_CODES.csv"],REQUIRED["FRS_NAICS_CODES.csv"])
        with f,db:
            for row in rows(r):
                naics["screened"]+=1;v=row["NAICS_CODE"].strip()
                if not re.fullmatch(r"[0-9]{6}",v):naics["missing_or_unrecognized_code"]+=1;continue
                sector=v[:3]
                if sector not in SECTORS:naics["other_industry_code"]+=1;continue
                key=registry_id(row["REGISTRY_ID"].strip())
                if key is None:naics["sector_code_unresolved_registry"]+=1;continue
                naics["sector_code_valid_registry"]+=1
                db.execute("INSERT OR IGNORE INTO health_codes VALUES(?,?)",(key,sector))
        require(naics["screened"]>0 and naics["screened"]==sum(naics[k] for k in ("missing_or_unrecognized_code","other_industry_code","sector_code_unresolved_registry","sector_code_valid_registry")),"NAICS row reconciliation")
        eligible={row[0] for row in db.execute("SELECT DISTINCT id FROM health_codes")}
        require(0<len(eligible)<=2_000_000,"health-sector classification count bound")
        fac=counters["FRS_FACILITIES.csv"];f,r=reader(z,ms["FRS_FACILITIES.csv"],REQUIRED["FRS_FACILITIES.csv"])
        with f,db:
            for row in rows(r):
                fac["screened"]+=1;key=registry_id(row["REGISTRY_ID"].strip())
                if key is None:fac["invalid_registry_key"]+=1;continue
                if db.execute("INSERT OR IGNORE INTO all_facilities VALUES(?)",(key,)).rowcount==0:
                    fac["duplicate_registry_key"]+=1
                    # Do not collapse inconsistent facility identities silently.
                    if key in eligible:raise ValueError("duplicate health-sector FRS facility key")
                    continue
                fac["unique_registry_key"]+=1
                if key in eligible:
                    state=row["FAC_STATE"].strip().upper()
                    state=state if re.fullmatch(r"[A-Z]{2}",state) else "unknown"
                    db.execute("INSERT INTO health_sites VALUES(?,?)",(key,state))
        require(fac["screened"]>0 and fac["screened"]==sum(fac[k] for k in ("invalid_registry_key","duplicate_registry_key","unique_registry_key")),"facility row reconciliation")
        require(db.execute("SELECT count(*) FROM all_facilities").fetchone()[0]==fac["unique_registry_key"],"unique facility count")
        valid_sites={r[0] for r in db.execute("SELECT id FROM health_sites")};require(valid_sites<=eligible and valid_sites,"health-sector join")
        pg=counters["FRS_PROGRAM_LINKS.csv"];f,r=reader(z,ms["FRS_PROGRAM_LINKS.csv"],REQUIRED["FRS_PROGRAM_LINKS.csv"])
        with f,db:
            for row in rows(r):
                pg["screened"]+=1;key=registry_id(row["REGISTRY_ID"].strip())
                if key not in valid_sites:pg["outside_resolved_health_sector"]+=1;continue
                acronym=code(row["PGM_SYS_ACRNM"])
                if acronym is None:pg["unrecognized_program"]+=1;continue
                pg["health_sector_program_observation"]+=1
                db.execute("INSERT OR IGNORE INTO health_programs VALUES(?,?)",(key,acronym))
        require(pg["screened"]>0 and pg["screened"]==sum(pg[k] for k in ("outside_resolved_health_sector","unrecognized_program","health_sector_program_observation")),"program link row reconciliation")
        check_integrity(db)
        by_sector={SECTORS[k]:n for k,n in db.execute("SELECT sector,count(*) FROM health_codes c JOIN health_sites s ON s.id=c.id GROUP BY sector")}
        by_state=dict(db.execute("SELECT state,count(*) FROM health_sites GROUP BY state"))
        by_program=dict(db.execute("SELECT program,count(*) FROM health_programs GROUP BY program"))
        require(sum(by_state.values())==len(valid_sites) and sum(by_sector.values())>=len(valid_sites) and sum(by_program.values())<=pg["health_sector_program_observation"],"aggregate count reconciliation")
        # No sub-state geography, facility-specific identity or site-program pairs.
        # Keep the social-assistance subsector separate from healthcare (621-623).
        health=db.execute("SELECT count(DISTINCT c.id) FROM health_codes c JOIN health_sites s ON s.id=c.id WHERE c.sector IN ('621','622','623')").fetchone()[0]
        return {"aggregate_rows":1,"source_rows_screened":sum(c["screened"] for c in counters.values()),"selected_members":{k:{"rows":dict(counters[k]),"uncompressed_bytes":ms[k].file_size,"zip_crc32":format(ms[k].CRC,"08x")} for k in REQUIRED},"distinct_sector62_registry_ids_in_naics":len(eligible),"resolved_sector62_registry_ids":len(valid_sites),"unresolved_sector62_registry_ids":len(eligible-valid_sites),"resolved_healthcare_621_623_registry_ids":health,"resolved_registry_id_counts_by_sector":by_sector,"sector62_registry_id_counts_by_state":by_state,"sector62_registry_id_counts_by_program":by_program,"distinct_health_sector_registry_program_pairs":sum(by_program.values()),"site_or_system_rows_retained":0,"program_pairs_retained":0,"scope":"EPA ECHO FRS subset; exact reported NAICS subsector code association and registry ID join. Multi-sector/program counts overlap; historical classifications may persist. Not a healthcare-facility census, current permit, compliance or ownership determination.","public_promotion":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ)
    store=storage.SourceAzure(os.environ)
    try:
        national=storage.national_manifest(store)
        with tempfile.TemporaryDirectory(prefix="frs-healthcare-") as d:
            root=Path(d);path=root/"source.zip";meta=download(path)
            result=storage.existing(store,KEY,meta["sha256"])
            if result is None:
                scratch=root/"temporary-keys.sqlite3";summary=qualify(path,scratch)
                require(sha(path)==meta["sha256"],"FRS source mutated")
                scratch.unlink();path.unlink();out=root/"projection.sqlite3";write_aggregate(out,summary)
                audit={"publisher":meta,"summary":summary,"projection_sha256":sha(out),"projection_bytes":out.stat().st_size,"reuse_review":"pending","public_promotion":False}
                result=storage.publish(store,KEY,meta,out,audit,root,national)
        with args.receipt.open("xb") as f:f.write(a.encode(result))
        print("PRIVATE_EPA_FRS_HEALTHCARE_COMPLETE",json.dumps(result,sort_keys=True),flush=True)
    finally:store.close()
if __name__=="__main__":main()
