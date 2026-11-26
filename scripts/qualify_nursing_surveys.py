"""Qualify two CMS nursing survey sources at the original record grain.

No facility addresses, individual findings, or row-level artifacts in CI.
No inferred compliance, risk score, procurement lead or equipment inventory.
"""
import argparse,csv,hashlib,io,json,os,re,sqlite3,tempfile
from collections import Counter,defaultdict
from contextlib import closing
from datetime import date,datetime,timezone
from pathlib import Path
import collect_cms as cms
from build_combined import require,readonly,sha,validate_base
from citation_evidence import BASE_SHA
RELEASE="2026-10-28"
PROCESSING="2026-10-01"
CCN="CMS Certification Number (CCN)"
DATES=[CCN,"Survey Date","Type of Survey","Survey Cycle","Processing Date"]
SUMMARY_HEAD=[CCN,"Provider Name","Provider Address","City/Town","State","ZIP Code","Inspection Cycle","Health Survey Date","Survey Footnote","Fire Safety Survey Date"]
SUMMARY_TOTALS=["Total Number of Health Deficiencies","Total Number of Fire Safety Deficiencies"]
CATEGORIES=["Freedom from Abuse and Neglect and Exploitation","Quality of Life and Care","Resident Assessment and Care Planning","Nursing and Physician Services","Resident Rights","Nutrition and Dietary","Pharmacy Service","Environmental","Administration","Infection Control","Emergency Preparedness","Automatic Sprinkler Systems","Construction","Services","Corridor Walls and Doors","Egress","Electrical","Emergency Plans and Fire Drills","Fire Alarm Systems","Smoke","Interior","Gas and Vacuum and Electrical Systems","Hazardous Area","Illumination and Emergency Power","Laboratories","Medical Gases and Anaesthetizing Areas","Smoking Regulations","Miscellaneous"]
SUMMARY_COUNTS=SUMMARY_TOTALS+["Count of "+c+" Deficiencies" for c in CATEGORIES]
SUMMARY=SUMMARY_HEAD+SUMMARY_COUNTS+["Location","Processing Date"]
SOURCES={"dates":("FS-034","svdt-c123",DATES),"summary":("FS-037","tbry-pc2d",SUMMARY)}
MAX_BYTES=80_000_000
MAX_ROWS=500000
TYPES={"Health Standard","Fire Safety Standard","Health Complaint","Fire Safety Complaint","Infection Control"}
def parse_date(raw,blank=False):
    s=raw.strip()
    if not s and blank:return None
    require(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",s) is not None,"date_shape")
    try:d=date.fromisoformat(s)
    except ValueError:raise ValueError("calendar_date") from None
    require(d<=date.fromisoformat(RELEASE),"date_after_release")
    return d.isoformat()

def cycle(raw):
    v=raw.strip()
    require(v in {"1","2","3"},"cycle_value")
    return int(v)

def numeric_count(raw):
    s=raw.strip()
    if not s:return None,"blank"
    if s.casefold() in {"n/a","na","not available","not applicable"}:return None,"missing_token"
    require(re.fullmatch(r"[0-9]{1,9}(?:\.0+)?",s) is not None,"count_value")
    n=int(s.split(".")[0])
    return n,"zero" if n==0 else "positive"

def download(key):
    sid,ident,header=SOURCES[key]
    meta=cms.metadata(ident);n=cms.count(ident)
    require(meta["released"]==RELEASE and 0<n<=MAX_ROWS,"unexpected source release/count")
    with cms.response(meta["url"]) as res:
        cms.allowed(res.geturl());data=res.read(MAX_BYTES+1)
    require(0<len(data)<=MAX_BYTES,"download bound")
    require(cms.metadata(ident)==meta and cms.count(ident)==n,"source changed during retrieval")
    return data,meta,n

def project(key,data,expected,db,providers):
    sid,ident,header=SOURCES[key]
    reader=csv.DictReader(io.StringIO(data.decode("utf-8-sig"),newline=""),strict=True)
    require(reader.fieldnames==header,"source_header_drift")
    table="inspection_dates" if key=="dates" else "survey_summary"
    db.execute("CREATE TABLE "+table+"(ordinal INTEGER PRIMARY KEY,row_sha TEXT NOT NULL,ccn TEXT NOT NULL,cycle INTEGER NOT NULL,processing TEXT NOT NULL,kind TEXT,date1 TEXT,date2 TEXT,health_count INTEGER,fire_count INTEGER,link_state TEXT NOT NULL)")
    rejects=Counter();links=Counter();classes=Counter();cycles=Counter();states=defaultdict(Counter);keys=Counter();digests=set();total=duplicates=0
    for total,row in enumerate(reader,1):
        require(total<=MAX_ROWS,"row bound")
        if None in row or any(v is None for v in row.values()):
            rejects["malformed_width"]+=1;continue
        digest=hashlib.sha256(json.dumps(list(row.values()),ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        if digest in digests:duplicates+=1
        digests.add(digest)
        field_states={}
        try:
            ccn=row[CCN].strip()
            require(re.fullmatch(r"[A-Z0-9]{6}",ccn) is not None,"ccn_shape")
            proc=parse_date(row["Processing Date"])
            require(proc==PROCESSING,"processing_date_mismatch")
            if key=="dates":
                cy=cycle(row["Survey Cycle"]);kind=row["Type of Survey"].strip()
                require(kind in TYPES,"survey_type")
                d1=parse_date(row["Survey Date"]);d2=None
                require(d1<=proc,"survey_after_processing")
                health=fire=None;candidate=(ccn,cy,kind,d1)
                link="ccn_present" if ccn in providers else "unmatched_ccn"
            else:
                cy=cycle(row["Inspection Cycle"]);kind="source_summary"
                state=row["State"].strip()
                require(re.fullmatch(r"[A-Z]{2}",state) is not None,"state_shape")
                d1=parse_date(row["Health Survey Date"],True);d2=parse_date(row["Fire Safety Survey Date"],True)
                require(all(d is None or d<=proc for d in (d1,d2)),"survey_after_processing")
                vals={}
                for field in SUMMARY_COUNTS:
                    vals[field],field_states[field]=numeric_count(row[field])
                health,fire=(vals[h] for h in SUMMARY_TOTALS);candidate=(ccn,cy)
                link="same_state" if state in providers.get(ccn,set()) else "state_conflict" if ccn in providers else "unmatched_ccn"
        except ValueError as e:
            reason=str(e)
            rejects[reason if reason in {"ccn_shape","date_shape","calendar_date","date_after_release","processing_date_mismatch","cycle_value","survey_type","survey_after_processing","state_shape","count_value"} else "unclassified_value"]+=1
            continue
        db.execute("INSERT INTO "+table+" VALUES(?,?,?,?,?,?,?,?,?,?,?)",(total,digest,ccn,cy,proc,kind,d1,d2,health,fire,link))
        keys[candidate]+=1;links[link]+=1;classes[kind]+=1;cycles[str(cy)]+=1
        for field,st in field_states.items():states[field][st]+=1
    db.commit()
    stored=db.execute("SELECT count(*) FROM "+table).fetchone()[0]
    require(total==expected==stored+sum(rejects.values()),"input reconciliation")
    require(stored==sum(links.values())==sum(classes.values())==sum(cycles.values())==sum(keys.values()),"projection reconciliation")
    require(all(sum(v.values())==stored for v in states.values()),"count field reconciliation")
    db.execute("CREATE INDEX "+table+"_ccn ON "+table+"(ccn)")
    require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite integrity")
    return {"source_id":sid,"dataset":ident,"columns":len(header),"input_rows":total,"stored_rows":stored,"rejected_rows":sum(rejects.values()),"reject_reasons":dict(rejects),
            "exact_duplicate_source_rows":duplicates,"repeated_candidate_key_rows":stored-len(keys),"distinct_ccns":db.execute("SELECT count(DISTINCT ccn) FROM "+table).fetchone()[0],
            "link_counts":dict(links),"source_classes":dict(classes),"cycle_counts":dict(cycles),"count_field_value_states":{k:dict(v) for k,v in states.items()},
            "retained_public_row_level_records":0,"limits":"Historical report-grain source observations; repeated candidate keys are not collapsed. Blank counts remain unknown. No compliance, vulnerability, equipment, procurement or current-operation inference."}

def compare_dates(db,base):
    dates=set(db.execute("SELECT DISTINCT ccn,date1 FROM inspection_dates"))
    # Same CCN/day corroboration only: survey type and event identity are not resolved.
    out=Counter()
    for ccn,day in base.execute("SELECT ccn,survey_date FROM findings WHERE dataset IN ('nursing-health','nursing-fire')"):
        out["same_ccn_day" if (ccn,day) in dates else "no_ccn_day_match"]+=1
    require(sum(out.values())==619069,"baseline citation reconciliation")
    return dict(out)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--cms-base",type=Path,required=True);p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    path=a.cms_base/"facilitysignal.sqlite3";require(not a.audit.exists() and sha(path)==BASE_SHA,"baseline or output mismatch")
    validate_base(a.cms_base)
    out={};failed=[]
    with closing(readonly(path)) as base, tempfile.TemporaryDirectory(prefix="nursing-survey-") as t, closing(sqlite3.connect(Path(t)/"survey.sqlite3")) as db:
        providers={}
        for ccn,state in base.execute("SELECT ccn,state FROM facilities WHERE dataset='nursing'"):providers.setdefault(ccn,set()).add(state)
        for key in SOURCES:
            try:
                data,meta,n=download(key);result=project(key,data,n,db,providers)
                result.update({"publisher":meta,"source_sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data),"retrieved_at":datetime.now(timezone.utc).isoformat(),"reuse_review":"pending"})
                if result["rejected_rows"] or not result["stored_rows"]:failed.append(key)
                if key=="summary" and result["repeated_candidate_key_rows"]:failed.append(key)
                out[key]=result
            except Exception as e:
                # Only fixed reason names; no values or network response contents.
                out[key]={"status":"failed","error_type":type(e).__name__};failed.append(key)
                print("NURSING_SURVEY_SOURCE_FAILED",key,type(e).__name__,flush=True)
        cross=compare_dates(db,base) if out.get("dates",{}).get("stored_rows",0)>0 and not out["dates"]["rejected_rows"] else None
    require(sha(path)==BASE_SHA,"baseline changed")
    audit={"baseline_sha256":BASE_SHA,"release":RELEASE,"sources":out,"citation_ccn_day_crosscheck":cross,
           "failed_sources":sorted(set(failed)),"retained_row_level_records":0,"limits":"Independent source projections in one temporary SQLite database; not a persistent integrated national dataset. No row-level publication. Source-specific reuse review pending."}
    a.audit.parent.mkdir(parents=True,exist_ok=True)
    with a.audit.open("x") as f:json.dump(audit,f,indent=2);f.write("\n")
    print("NURSING_SURVEYS_AUDIT",json.dumps(audit),flush=True)
    require(not failed and len(out)==2,"source anomalies require review")
if __name__=="__main__":main()
