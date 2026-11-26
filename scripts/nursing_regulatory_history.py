"""Read-only local search of five archived nursing regulatory source grains.

No publisher retrieval, Azure writes, public row output or current-risk inference.
"""
import argparse
import json
import os
import re
import tempfile
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path

import azure_national_archive as archive
from build_combined import require, readonly, sha, check_integrity
from citation_evidence import correction_state, date_state
from scripts import audit_azure_archive_inventory as inventory
from scripts import azure_verified_extension as ext
from scripts import recover_azure_extension as recovery
from scripts.qualify_nursing_surveys import TYPES

ROOT=Path(__file__).resolve().parents[1]
BASE_SHA="138ad57c3719fe63895eeaff702c04b51107fe1cf6dc4daf403a554985a1f033"
EXT_SHA="4090f140a45bdee990a0669e357d6d8d4672aff829ff0e52fb8f34e2e5d7e9bf"
EXPECTED={"health_citations":418682,"fire_citations":200387,"survey_dates":148956,"survey_summary":43931,"penalties":15007}
EXT_IDS={"survey_dates":"FS-034","survey_summary":"FS-037","penalties":"FS-036"}
CITATIONS={"health_citations":"nursing-health","fire_citations":"nursing-fire"}
TABLES={"survey_dates":"inspection_dates","survey_summary":"survey_summary","penalties":"penalty"}
RELEASE="2026-10-28"
LIMITS="Historical source observations, not unique inspections or outstanding violations. Exact source CCN/state or explicitly labelled CCN-only candidate. Reported correction and fine amounts are not verified remediation or outstanding liability."


def day(raw):
    require(isinstance(raw,str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",raw) is not None,"ISO calendar date required")
    try:return date.fromisoformat(raw).isoformat()
    except ValueError:raise ValueError("invalid calendar date") from None


def sql_day(raw):
    if not raw:return None
    try:return day(raw)
    except ValueError:return None


def identity(base,ccn,state):
    require(isinstance(ccn,str) and re.fullmatch(r"[A-Z0-9]{6}",ccn) and isinstance(state,str) and re.fullmatch(r"[A-Z]{2}",state),"exact nursing CCN and state required")
    require(base.execute("SELECT state FROM facilities WHERE dataset='nursing' AND ccn=?",(ccn,)).fetchall()==[(state,)],"no unique same-state nursing directory record")


def pinned_paths(base_path,extension_path):
    require(base_path.is_file() and extension_path.is_file() and not base_path.is_symlink() and not extension_path.is_symlink(),"regular private archive paths required")
    require(sha(base_path)==BASE_SHA and sha(extension_path)==EXT_SHA,"archive checksum mismatch")


def source_query(base,extension,source,ccn,state,start=None,end=None,kind=None,cycle=None,summary_date=None):
    require(source in EXPECTED,"unsupported regulatory source")
    identity(base,ccn,state)
    require(summary_date is None or (source=="survey_summary" and summary_date in ("health","fire")),"summary date field must be health or fire")
    require(source!="survey_summary" or not (start or end) or summary_date is not None,"select health or fire summary date for date bounds")
    require(cycle is None or (source in ("survey_dates","survey_summary") and type(cycle) is int and cycle in (1,2,3)),"cycle applies only to survey sources")
    if start is not None:start=day(start)
    if end is not None:end=day(end)
    require(start is None or end is None or start<=end,"invalid date range")
    if kind is not None:
        allowed=TYPES if source=="survey_dates" else {"Fine","Payment Denial"} if source=="penalties" else set()
        require(kind in allowed,"unsupported source-native kind")
    if source in CITATIONS:
        db=base;cols="row_hash,ccn,state,survey_date,survey_type,correction_status,correction_date"
        names=("source_row_sha256","ccn","reported_state","survey_date","survey_type","source_correction_status","source_correction_date")
        where=["dataset=?","ccn=?","state=?","release_id=(SELECT release_id FROM current_release WHERE dataset=?)"]
        args=[CITATIONS[source],ccn,state,CITATIONS[source]]
        table="findings";date_col="survey_date";tie="row_hash"
    elif source=="penalties":
        db=extension;cols="row_number,ccn,state,penalty_date,kind,fine_amount,denial_start,denial_days,processing_date,link_state"
        names=("source_ordinal","ccn","reported_state","penalty_date","kind","reported_fine_amount_usd","reported_denial_start","reported_denial_days","processing_date","archived_link_state")
        where=["ccn=?","state=?","link_state='same_state'"];args=[ccn,state]
        table="penalty";date_col="penalty_date";tie="row_number"
    else:
        db=extension;table=TABLES[source];tie="ordinal";date_col="date2" if summary_date=="fire" else "date1"
        cols="ordinal,ccn,cycle,processing,kind,date1,date2,health_count,fire_count,link_state"
        names=("source_ordinal","ccn","cycle","processing_date","kind","survey_date" if source=="survey_dates" else "health_survey_date","secondary_date" if source=="survey_dates" else "fire_survey_date","reported_health_count","reported_fire_count","archived_link_state")
        where=["ccn=?","link_state=?"];args=[ccn,"ccn_present" if source=="survey_dates" else "same_state"]
    if kind is not None:where.append("kind=?");args.append(kind)
    if cycle is not None:where.append("cycle=?");args.append(cycle)
    if start is not None:where.append("qualified_day("+date_col+")>=?");args.append(start)
    if end is not None:where.append("qualified_day("+date_col+")<=?");args.append(end)
    db.create_function("qualified_day",1,sql_day,deterministic=True)
    return db,cols,names," FROM "+table+" WHERE "+" AND ".join(where),args," ORDER BY qualified_day("+date_col+") DESC, "+tie


def search(base,extension,source,ccn,state,start=None,end=None,kind=None,cycle=None,summary_date=None,page=1,limit=25):
    require(type(page) is int and 1<=page<=100000 and type(limit) is int and 1<=limit<=100,"pagination bounds")
    db,cols,names,clause,args,order=source_query(base,extension,source,ccn,state,start,end,kind,cycle,summary_date)
    total=db.execute("SELECT count(*)"+clause,args).fetchone()[0]
    records=[]
    for row in db.execute("SELECT "+cols+clause+order+" LIMIT ? OFFSET ?",(*args,limit,(page-1)*limit)):
        item=dict(zip(names,row))
        item.update({"source":source,"source_release":RELEASE,"directory_candidate_state":state})
        if source in CITATIONS:
            item["link_evidence"]="exact_source_ccn_and_reported_state"
            item["correction_evidence"]=correction_state(item["source_correction_status"])
            item["correction_date_evidence"]=date_state(item["source_correction_date"],date.fromisoformat(RELEASE))
        elif source=="penalties":item["link_evidence"]="exact_source_ccn_and_reported_state"
        else:
            item["reported_state"]=None
            item["link_evidence"]="ccn_only_directory_candidate" if source=="survey_dates" else "prior_same_state_check_raw_state_not_retained"
        records.append(item)
    return {"source":source,"ccn":ccn,"directory_state":state,"source_record_matches":total,"page":page,"limit":limit,"summary_date_field":summary_date,"records":records,"scope":LIMITS,"current_enforcement_status":"unknown"}


def profile(base,extension,ccn,state):
    return {"ccn":ccn,"directory_state":state,"sources":{s:search(base,extension,s,ccn,state,limit=5) for s in EXPECTED},"scope":LIMITS,"current_enforcement_status":"unknown","canonical_merges":0}


def qualify(base,extension):
    check_integrity(base);check_integrity(extension)
    rows=base.execute("SELECT ccn,state FROM facilities WHERE dataset='nursing' ORDER BY ccn,state").fetchall()
    require(len(rows)==14686 and len({ccn for ccn,_ in rows})==len(rows),"nursing directory identity pin")
    directory=dict(rows);details={};direct={s:Counter() for s in EXPECTED};direct_dates=Counter()
    cutoff=date.fromisoformat(RELEASE)
    for source,dataset in CITATIONS.items():
        release=base.execute("SELECT r.id,r.published_on FROM current_release c JOIN releases r ON r.id=c.release_id WHERE c.dataset=? AND r.dataset=c.dataset",(dataset,)).fetchone()
        require(release and release[1]==RELEASE,"citation source release pin")
        fields={"linkage":Counter(),"correction":Counter(),"survey_date":Counter(),"correction_date":Counter()}
        for ccn,state,sd,cs,cd,rid in base.execute("SELECT ccn,state,survey_date,correction_status,correction_date,release_id FROM findings WHERE dataset=?",(dataset,)):
            require(rid==release[0],"mixed citation release")
            linked=directory.get(ccn)==state
            fields["linkage"]["same_ccn_state" if linked else "unresolved"]+=1
            fields["correction"][correction_state(cs)]+=1
            fields["survey_date"][date_state(sd,cutoff)]+=1
            fields["correction_date"][date_state(cd,cutoff)]+=1
            if linked:direct[source][ccn]+=1
            direct_dates[(ccn,sd)]+=1
        require(all(sum(v.values())==EXPECTED[source] for v in fields.values()),"citation count reconciliation")
        details[source]={"source_rows":EXPECTED[source],"matched_directory_candidates":sum(direct[source].values()),"distributions":{k:dict(v) for k,v in fields.items()}}
    source_pins=recovery.load_pin()["source_log_results"]
    for source,table in TABLES.items():
        sid=EXT_IDS[source]
        meta=extension.execute("SELECT table_name,rows,source_sha256 FROM extension_sources WHERE source_id=?",(sid,)).fetchone()
        require(meta and meta[0]==table and meta[1]==EXPECTED[source],"extension source lineage")
        pin=source_pins[sid]
        require(pin["source_sha256"]==meta[2] and pin["rows"]==meta[1],"extension source digest pin")
        kinds=Counter();links=Counter();dates=Counter();values=Counter()
        if source=="penalties":
            for ccn,state,kind,pd,amount,start,days,link in extension.execute("SELECT ccn,state,kind,penalty_date,fine_amount,denial_start,denial_days,link_state FROM penalty"):
                linked=directory.get(ccn)==state
                require(link==("same_state" if linked else "state_conflict" if ccn in directory else "unmatched_ccn"),"penalty linkage mismatch")
                if linked:direct[source][ccn]+=1
                require(kind in {"Fine","Payment Denial"},"unexpected penalty kind")
                kinds[kind]+=1;links[link]+=1;dates[date_state(pd or "",cutoff)]+=1
                if kind=="Fine":values["fine_amount_missing" if amount is None else "fine_amount_reported"]+=1
                else:values["denial_days_missing" if days is None else "denial_days_reported"]+=1
        else:
            for ccn,kind,cycle,d1,d2,h,f,link in extension.execute("SELECT ccn,kind,cycle,date1,date2,health_count,fire_count,link_state FROM "+table):
                require(cycle in (1,2,3),"unexpected survey cycle")
                require(kind in TYPES if source=="survey_dates" else kind=="source_summary","unexpected survey kind")
                require(link in ({"ccn_present","unmatched_ccn"} if source=="survey_dates" else {"same_state","state_conflict","unmatched_ccn"}),"unexpected archived linkage")
                if link==("ccn_present" if source=="survey_dates" else "same_state"):
                    require(ccn in directory,"missing archived directory candidate")
                    direct[source][ccn]+=1
                kinds[kind]+=1;links[link]+=1;dates[date_state(d1 or "",cutoff)]+=1
                if source=="survey_summary":
                    for name,value in (("health",h),("fire",f)):
                        require(value is None or type(value) is int and value>=0,"unexpected reported deficiency count")
                        values[name+("_missing" if value is None else "_zero" if value==0 else "_positive")]+=1
        require(sum(kinds.values())==sum(links.values())==sum(dates.values())==EXPECTED[source],"extension row reconciliation")
        require(dict(links)==pin["link_counts"],"prior source-link audit mismatch")
        details[source]={"source_id":sid,"source_rows":EXPECTED[source],"matched_directory_candidates":sum(direct[source].values()),"source_sha256":meta[2],"source_kinds":dict(kinds),"archived_link_states":dict(links),"primary_date_states":dict(dates),"value_states":dict(values)}
    survey_days=set(extension.execute("SELECT DISTINCT ccn,date1 FROM inspection_dates"))
    require(sum(n for key,n in direct_dates.items() if key in survey_days)==619069,"historical same-CCN/day corroboration differs")
    samples={ccn for ccn,_ in rows[::max(1,len(rows)//16)]}
    for s in EXPECTED:
        if direct[s]:samples.add(max(direct[s],key=lambda k:(direct[s][k],k)))
    checks=0
    for ccn in sorted(samples):
        state=directory[ccn]
        for source in EXPECTED:
            a=search(base,extension,source,ccn,state,limit=3);b=search(base,extension,source,ccn,state,page=2,limit=3)
            require(a["source_record_matches"]==b["source_record_matches"]==direct[source][ccn],"query versus independent source scan")
            require(len(a["records"])+len(b["records"])==min(6,direct[source][ccn]),"pagination reconciliation")
            k="source_row_sha256" if source in CITATIONS else "source_ordinal"
            require(len({v[k] for v in a["records"]+b["records"]})==len(a["records"])+len(b["records"]),"duplicate page records")
            checks+=1
    return {"status":"PASS","scope":LIMITS,"sources":details,"nursing_directory_source_records":len(rows),"source_records_checked":sum(EXPECTED.values()),"same_ccn_day_citation_rows":619069,"sample_provider_queries":checks,"provider_candidate_coverage":{s:len(v) for s,v in direct.items()},"publisher_downloads":0,"azure_writes":0,"new_source_records":0,"public_promotion":False,"canonical_merges":0}


def run_qualification(receipt):
    archive.run_key(os.environ);store=inventory.ReadOnlyAzure(os.environ)
    try:
        national=ext.national_manifest(store)
        with tempfile.TemporaryDirectory(prefix="nursing-regulatory-history-") as tmp:
            root=Path(tmp);base_path,_=ext.restore_national(store,national,root/"national")
            pointer,psha,phead=ext.read_small(store,ext.EXT_POINTER)
            rec,rsha,rhead=ext.read_small(store,pointer["receipt"],pointer["receipt_sha256"])
            pin=recovery.load_pin();records=recovery.validate_receipt(rec,national,pin)
            require(pointer["release"]==pin["release"] and pointer["receipt"]==recovery.COMPLETE,"extension pointer scope")
            for f in records:ext.fetch_verified(store,rec["payload_prefix"]+"/"+f["path"],f,root/f["path"])
            require(sha(root/"expanded-source-lock.json")==sha(ROOT/"research/expanded_source_lock_20261126.json"),"extension lock mismatch")
            extension_path=root/"extension.sqlite3"
            recovery.verify_db(extension_path,json.loads((root/"extension-audit.json").read_text()),rec,pin,base_path)
            pinned_paths(base_path,extension_path)
            with closing(readonly(base_path)) as base,closing(readonly(extension_path)) as extension:result=qualify(base,extension)
            pinned_paths(base_path,extension_path);ext.unchanged(store,national)
            require(ext.read_small(store,ext.EXT_POINTER,psha)[2]==phead and ext.read_small(store,pointer["receipt"],rsha)[2]==rhead,"extension evidence changed")
            result.update({"national_database_sha256":BASE_SHA,"extension_database_sha256":EXT_SHA,"national_receipt_sha256":national["receipt_sha256"],"extension_receipt_sha256":rsha})
    finally:store.close()
    with receipt.open("xb") as out:out.write(archive.encode(result))
    print("FACILITYSIGNAL_NURSING_REGULATORY_HISTORY_QUALIFIED",json.dumps(result,sort_keys=True),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="command",required=True)
    q=sub.add_parser("qualify");q.add_argument("--receipt",type=Path,required=True)
    for command in ("search","profile"):
        q=sub.add_parser(command);q.add_argument("--national",type=Path,required=True);q.add_argument("--extension",type=Path,required=True);q.add_argument("--ccn",required=True);q.add_argument("--state",required=True)
        if command=="search":
            q.add_argument("--source",choices=sorted(EXPECTED),required=True);q.add_argument("--start");q.add_argument("--end");q.add_argument("--kind");q.add_argument("--cycle",type=int);q.add_argument("--summary-date",choices=("health","fire"));q.add_argument("--page",type=int,default=1);q.add_argument("--limit",type=int,default=25)
    args=p.parse_args()
    if args.command=="qualify":
        require(not args.receipt.exists(),"receipt already exists");run_qualification(args.receipt);return
    pinned_paths(args.national,args.extension)
    with closing(readonly(args.national)) as base,closing(readonly(args.extension)) as extension:
        if args.command=="profile":result=profile(base,extension,args.ccn,args.state)
        else:result=search(base,extension,args.source,args.ccn,args.state,args.start,args.end,args.kind,args.cycle,args.summary_date,args.page,args.limit)
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":main()
