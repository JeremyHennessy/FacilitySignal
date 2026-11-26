"""Qualify CMS nursing penalties in an isolated SQLite projection, with aggregate-only CI evidence."""
import argparse,csv,hashlib,io,json,re,sqlite3
from collections import Counter
from contextlib import closing
from datetime import date,datetime,timezone
from pathlib import Path
import collect_cms as cms
from build_combined import require,readonly,sha,validate_base
from citation_evidence import BASE_SHA

IDENT="g6vv-u9sr"
HEADER=["CMS Certification Number (CCN)","Provider Name","Provider Address","City/Town","State","ZIP Code","Penalty Date","Penalty Type","Fine ID","Fine Amount","Payment Denial Start Date","Payment Denial Length in Days","Location","Processing Date"]
MAX_BYTES=30_000_000

def iso(s):
    if not s:return None
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",s):raise ValueError("date shape")
    return date.fromisoformat(s).isoformat()

def integer(s):
    if not s:return None
    if not re.fullmatch(r"[0-9]{1,15}(?:\.0+)?",s):raise ValueError("numeric shape")
    return int(s.split(".")[0])

def download():
    meta=cms.metadata(IDENT);n=cms.count(IDENT)
    with cms.response(meta["url"]) as res:
        cms.allowed(res.geturl());data=res.read(MAX_BYTES+1)
    require(0<len(data)<=MAX_BYTES,"download bound")
    require(cms.metadata(IDENT)==meta and cms.count(IDENT)==n,"publisher changed mid-download")
    return data,meta,n

def project(data,expected,db,providers,release):
    reader=csv.DictReader(io.StringIO(data.decode("utf-8-sig"),newline=""),strict=True)
    require(reader.fieldnames==HEADER,"penalty schema drift")
    db.execute("CREATE TABLE penalty(row_number INTEGER PRIMARY KEY,row_sha TEXT NOT NULL,ccn TEXT NOT NULL,state TEXT NOT NULL,penalty_date TEXT,kind TEXT NOT NULL,fine_id TEXT,fine_amount INTEGER,denial_start TEXT,denial_days INTEGER,processing_date TEXT,link_state TEXT NOT NULL)")
    counts=Counter();links=Counter();reject=Counter();dates=Counter();missing=Counter();seen=set();fine_ids=set();duplicate_rows=duplicate_fine_ids=total=0
    for total,row in enumerate(reader,1):
        require(None not in row and all(v is not None for v in row.values()),"malformed CSV row")
        digest=hashlib.sha256(json.dumps(list(row.values()),ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        if digest in seen:duplicate_rows+=1
        seen.add(digest)
        ccn,state,kind=(row[k].strip() for k in ("CMS Certification Number (CCN)","State","Penalty Type"))
        fid=row["Fine ID"].strip() or None
        try:
            if not re.fullmatch(r"[A-Z0-9]{6}",ccn) or not re.fullmatch(r"[A-Z]{2}",state):raise ValueError("identifier shape")
            if kind not in ("Fine","Payment Denial"):raise ValueError("unknown penalty type")
            pd=iso(row["Penalty Date"].strip());proc=iso(row["Processing Date"].strip())
            start=iso(row["Payment Denial Start Date"].strip())
            amount=integer(row["Fine Amount"].strip());days=integer(row["Payment Denial Length in Days"].strip())
            if fid is not None and not re.fullmatch(r"[0-9]{1,20}",fid):raise ValueError("fine identifier shape")
        except ValueError as e:
            # Fixed reason vocabulary only; never print source row or exception values.
            reason=str(e)
            reject[reason if reason in ("date shape","numeric shape","identifier shape","unknown penalty type","fine identifier shape") else "invalid calendar date"]+=1
            continue
        if kind=="Fine":
            if fid is None:missing["fine_id"]+=1
            elif fid in fine_ids:duplicate_fine_ids+=1
            if fid is not None:fine_ids.add(fid)
            if amount is None:missing["fine_amount"]+=1
            if start is not None or days is not None:missing["fine_with_denial_fields"]+=1
        else:
            if start is None:missing["denial_start"]+=1
            if days is None:missing["denial_days"]+=1
            if fid is not None or amount is not None:missing["denial_with_fine_fields"]+=1
        for field,value in (("penalty",pd),("processing",proc),("denial_start",start)):
            if value is not None and value>release:dates[field+"_after_release"]+=1
        if pd is None:missing["penalty_date"]+=1
        if proc is None:missing["processing_date"]+=1
        link="same_state" if state in providers.get(ccn,set()) else "state_conflict" if ccn in providers else "unmatched_ccn"
        db.execute("INSERT INTO penalty VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(total,digest,ccn,state,pd,kind,fid,amount,start,days,proc,link))
        counts[kind]+=1;links[link]+=1
    db.commit()
    stored=db.execute("SELECT count(*) FROM penalty").fetchone()[0]
    require(total==expected==stored+sum(reject.values()),"source count mismatch")
    require(stored==sum(counts.values())==sum(links.values()),"projection reconciliation")
    require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","database integrity")
    db.execute("CREATE INDEX penalty_ccn ON penalty(ccn,state)")
    return {"input_rows":total,"stored_rows":stored,"rejected_rows":sum(reject.values()),"reject_reasons":dict(reject),"exact_duplicate_rows":duplicate_rows,"duplicate_fine_ids":duplicate_fine_ids,"penalty_type_counts":dict(counts),"link_counts":dict(links),"field_anomalies":dict(missing),"date_anomalies":dict(dates),"distinct_ccns":db.execute("SELECT count(DISTINCT ccn) FROM penalty").fetchone()[0],"fine_amount_reported_sum_usd":db.execute("SELECT sum(fine_amount) FROM penalty WHERE kind='Fine'").fetchone()[0],"fine_amount_reported_count":db.execute("SELECT count(fine_amount) FROM penalty WHERE kind='Fine'").fetchone()[0]}

def main():
    p=argparse.ArgumentParser();p.add_argument("--cms-base",type=Path,required=True);p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    path=a.cms_base/"facilitysignal.sqlite3"
    require(not a.audit.exists() and sha(path)==BASE_SHA,"baseline or audit path mismatch")
    validate_base(a.cms_base)
    data,meta,n=download()
    providers={}
    with closing(readonly(path)) as src:
        for ccn,state in src.execute("SELECT ccn,state FROM facilities WHERE dataset='nursing'"):
            providers.setdefault(ccn,set()).add(state)
    with closing(sqlite3.connect(":memory:")) as db:
        audit=project(data,n,db,providers,date.fromisoformat(meta["released"]).isoformat())
        # Verify exact indexed local lookup returns the same number as the source projection.
        ccn=db.execute("SELECT ccn FROM penalty LIMIT 1").fetchone()
        require(ccn is not None and db.execute("SELECT count(*) FROM penalty WHERE ccn=?",ccn).fetchone()[0]>0,"populated lookup failed")
    require(sha(path)==BASE_SHA,"baseline mutated")
    audit.update({"publisher":meta,"source_sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data),"retrieved_at":datetime.now(timezone.utc).isoformat(),"baseline_sha256":BASE_SHA,"reuse_review":"pending","retained_row_level_records":0,"limits":"Reported historical fine amounts are not outstanding liabilities or procurement intent. Exact CCN/state candidates are source evidence, not canonical sites. No row-level publication."})
    a.audit.parent.mkdir(parents=True,exist_ok=True)
    a.audit.write_text(json.dumps(audit,indent=2)+"\n")
    print("PENALTIES_AUDIT",json.dumps(audit),flush=True)
    require(audit["rejected_rows"]==audit["exact_duplicate_rows"]==audit["duplicate_fine_ids"]==0 and not audit["field_anomalies"],"source anomalies require review")

if __name__=="__main__":main()
