"""Import a qualified CMS QCOR hospital workbook's structured survey and tag projection.

No narrative columns are stored or logged. Source rows, not deduplicated citations.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
import facilitysignal as fs

HEADER=("CCN","Facility Name","Hospital Subtype","Street Address","City","State/Territory","ZIP",
        "CMS Region","Survey Event ID","Survey Date","Survey Type","Deficiency Tag","Deficiency Description",
        "Deficiency Tag Type",*("Statement of Deficiency Text (Part "+str(i)+")" for i in range(1,5)))
URL="https://qcor.cms.gov/downloadHospital2567"
SHEET="Hospital 2567s"

def text_field(value,limit=300):
    if value is None: return ""
    value=str(value).strip()
    if len(value)>limit or "\x00" in value: raise ValueError("oversize_or_invalid_structured_field")
    return value

def identifier(value,*,ccn=False):
    if isinstance(value,int) and not isinstance(value,bool) and 0<=value<=999999:
        value=str(value).zfill(6) if ccn else str(value)
    s=text_field(value,32).upper()
    if ccn:
        if not re.fullmatch(r"[A-Z0-9]{6}",s): raise ValueError("invalid_ccn")
    elif not re.fullmatch(r"[A-Z0-9]{6}",s):
        raise ValueError("invalid_or_ambiguous_event_id")
    return s

def survey_date(value):
    if isinstance(value,datetime): return value.date().isoformat()
    if isinstance(value,date): return value.isoformat()
    s=text_field(value,32)
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%m/%d/%y"):
        try: return datetime.strptime(s,fmt).date().isoformat()
        except ValueError: pass
    raise ValueError("invalid_survey_date")

def project(values):
    # Only the first 14 source fields are inspected by this projection.
    # Read-only XLSX iteration can omit trailing empty cells. The exact header
    # is checked separately; reject extra columns and restore missing trailing blanks.
    if len(values)>len(HEADER): raise ValueError("wrong_column_count")
    values=tuple(values)+(None,)*(len(HEADER)-len(values))
    ccn=identifier(values[0],ccn=True)
    name=text_field(values[1])
    if not name: raise ValueError("missing_facility_name")
    event=identifier(values[8])
    day=survey_date(values[9])
    tag=text_field(values[11],40).upper()
    description=text_field(values[12],500)
    tag_type=text_field(values[13],100)
    if not tag and (description or tag_type): raise ValueError("missing_tag_with_description")
    is_memo=bool(tag_type.lower()=="memo" or re.fullmatch(r"[A-Z]0{4}",tag))
    kind="memo" if is_memo else "tag" if tag else "no_tag_reported"
    return (ccn,name,text_field(values[2]),text_field(values[3]),text_field(values[4]),
            text_field(values[5],80).upper(),text_field(values[6],30),text_field(values[7],80),
            event,day,text_field(values[10],150),tag,description,tag_type,kind)

def import_workbook(db_path,workbook,meta,expected):
    import openpyxl
    if expected<1: raise ValueError("positive expected row count required")
    fs.init(db_path)
    book=openpyxl.load_workbook(workbook,read_only=True,data_only=True,keep_links=False)
    stats=Counter()
    reject=Counter()
    try:
        if book.sheetnames!=[SHEET]: raise ValueError("unexpected workbook sheet names")
        sheet=book[SHEET];sheet.reset_dimensions()
        iterator=sheet.iter_rows(values_only=True)
        if tuple(next(iterator,()))!=HEADER: raise ValueError("header schema changed")
        with closing(fs.connect(db_path)) as db,db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM qcor_hospital_releases WHERE source_sha256=?",(meta["sha256"],)).fetchone():
                raise ValueError("identical release already exists")
            release=db.execute("INSERT INTO qcor_hospital_releases(source_sha256,retrieved_at,download_url,byte_count,expected_rows,stored_rows) VALUES(?,?,?,?,?,0)",
                               (meta["sha256"],meta["retrieved_at"],URL,meta["bytes"],expected)).lastrowid
            batch=[]
            for ordinal,values in enumerate(iterator,2):
                if not any(v is not None and v!="" for v in values): continue
                stats["input_rows"]+=1
                try: projected=project(values)
                except ValueError as exc:
                    reject[str(exc)]+=1
                    continue
                stats["numeric_ccn_rows"]+=isinstance(values[0],int) and not isinstance(values[0],bool)
                stats[projected[-1]]+=1
                digest=hashlib.sha256(json.dumps(projected,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
                batch.append((release,ordinal,digest,*projected))
                if len(batch)>=5000:
                    db.executemany("INSERT INTO qcor_hospital_rows VALUES("+",".join("?" for _ in range(18))+")",batch)
                    batch.clear()
            if batch: db.executemany("INSERT INTO qcor_hospital_rows VALUES("+",".join("?" for _ in range(18))+")",batch)
            stats["rejected_rows"]=sum(reject.values())
            if stats["input_rows"]!=expected or reject:
                print("QCOR_REJECT_SUMMARY",json.dumps({"input_rows":stats["input_rows"],"expected":expected,"rejected":reject}),flush=True)
                raise ValueError("count/schema qualification failed; transaction rolled back")
            n=db.execute("SELECT count(*) FROM qcor_hospital_rows WHERE release_id=?",(release,)).fetchone()[0]
            if n!=expected: raise ValueError("stored row reconciliation failed")
            db.execute("UPDATE qcor_hospital_releases SET stored_rows=? WHERE id=?",(n,release))
            db.execute("INSERT INTO qcor_hospital_current VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET release_id=excluded.release_id",(release,))
            groups=db.execute("""SELECT count(*) FROM (SELECT ccn,event_id,survey_date FROM qcor_hospital_rows WHERE release_id=? GROUP BY ccn,event_id,survey_date)""",(release,)).fetchone()[0]
            unique_ccn=db.execute("SELECT count(DISTINCT ccn) FROM qcor_hospital_rows WHERE release_id=?",(release,)).fetchone()[0]
            duplicate_projection=n-db.execute("SELECT count(DISTINCT projection_sha256) FROM qcor_hospital_rows WHERE release_id=?",(release,)).fetchone()[0]
            # Count distinct historical source events, not a confirmed open-violation count.
            memo_only=db.execute("""SELECT count(*) FROM (
                SELECT ccn,event_id,survey_date FROM qcor_hospital_rows WHERE release_id=?
                GROUP BY ccn,event_id,survey_date HAVING SUM(CASE WHEN row_kind='tag' THEN 1 ELSE 0 END)=0
                )""",(release,)).fetchone()[0]
            states=fs.rows(db,"SELECT state,count(*) AS rows FROM qcor_hospital_rows WHERE release_id=? GROUP BY state ORDER BY state",(release,))
            if db.execute("PRAGMA foreign_key_check").fetchone() or db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise ValueError("DB integrity failed")
        return {"stored_rows":n,"survey_event_keys":groups,"unique_ccns":unique_ccn,
                "duplicate_projection_rows_retained":duplicate_projection,"events_without_nonmemo_tags":memo_only,
                "row_kinds":{k:stats[k] for k in ("tag","memo","no_tag_reported")},
                "numeric_ccn_rows":stats["numeric_ccn_rows"],"rejected_rows":stats["rejected_rows"],
                "states":states}
    finally:
        book.close()

def main():
    from scripts.probe_qcor_hospital import download
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--expected-rows",type=int,required=True)
    p.add_argument("--base-db",type=Path)
    args=p.parse_args()
    out=args.output.resolve()
    if out.exists(): p.error("output directory must be new")
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".qcor-stage-",dir=out.parent) as tmp:
        temp=Path(tmp);ready=temp/"ready";ready.mkdir()
        workbook=temp/"hospital.xlsx"
        meta=download(workbook)
        meta["retrieved_at"]=datetime.now(timezone.utc).isoformat()
        db=ready/"facilitysignal.sqlite3"
        if args.base_db:
            base=args.base_db.resolve()
            if not base.is_file(): raise ValueError("base db missing")
            with closing(sqlite3.connect(base.as_uri()+"?mode=ro",uri=True)) as src,closing(sqlite3.connect(db)) as dst:
                if src.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise ValueError("base DB integrity")
                src.backup(dst)
        result=import_workbook(db,workbook,meta,args.expected_rows)
        with db.open("rb") as f: db_hash=hashlib.file_digest(f,"sha256").hexdigest()
        audit={"source_id":"FS-020","source":meta,"expected_rows":args.expected_rows,**result,"db_sha256":db_hash,
               "note":"Source rows retained, narrative omitted, source release date unknown; status/correction unknown. Workbook count pinned to observed source probe, not independent publisher version stats."}
        (ready/"qcor-hospital-manifest.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        os.rename(ready,out)
        print("QCOR_IMPORTED",json.dumps(audit),flush=True)

if __name__=="__main__": main()
