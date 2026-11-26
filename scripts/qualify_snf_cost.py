"""Qualify the CMS skilled nursing facility 2024 selected cost report; aggregate evidence only.

Do not interpret an asset balance as installed equipment, a vendor payment, a
purchase plan, or present facility status. Preserve original report periods.
"""
import argparse,csv,hashlib,io,json,re,sqlite3,tempfile
from collections import Counter,defaultdict
from contextlib import closing
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit
import collect_registry as registry
from build_combined import require,readonly,sha,validate_base
from citation_evidence import BASE_SHA

TITLE="Skilled Nursing Facility Cost Report"
PERIOD="2024-01-01/2024-12-31"
MAX_BYTES=35_000_000
CORE=["rpt_rec_num","Provider CCN","State Code","Fiscal Year Begin Date","Fiscal Year End Date"]
MEASURES=["Number of Beds","Total Bed Days Available","Total Days Total","Total Costs","Total Charges",
          "Overhead Non-Salary Costs","Total Salaries From Worksheet A","Contract Labor",
          "Land","Land Improvements","Buildings","Leasehold Improvements","Fixed Equipment","Major Movable Equipment",
          "Total Current Assets"]
MISSING={"","not available","n/a","na","null","not applicable"}

def norm(s):
    return s.strip().casefold()

def select(catalog):
    matches=[d for d in catalog.get("dataset",[]) if d.get("title")==TITLE]
    require(len(matches)==1 and matches[0].get("accessLevel")=="public","catalog title/access")
    d=matches[0];dist=d.get("distribution",[])
    versions=[x for x in dist if x.get("format","").upper()=="API" and x.get("temporal")==PERIOD
              and str(x.get("description","")).casefold()!="latest" and x.get("accessURL")]
    require(len(versions)==1,"ambiguous 2024 version-specific API")
    api=registry.allowed(versions[0]["accessURL"])
    m=re.fullmatch(r"https://data\.cms\.gov/data-api/v1/dataset/([0-9a-f-]{36})/data",api)
    require(m is not None,"unexpected version API URL")
    files=[x for x in dist if x.get("temporal")==PERIOD and x.get("downloadURL")
           and (x.get("format","").upper()=="CSV" or x.get("mediaType")=="text/csv")]
    require(len(files)==1,"ambiguous 2024 CSV distribution")
    url=registry.allowed(files[0]["downloadURL"])
    require(urlsplit(url).path.lower().endswith(".csv"),"unexpected file type")
    return {"title":TITLE,"period":PERIOD,"version":m.group(1),"api":api,"url":url,
            "modified":d.get("modified"),"license":d.get("license"),
            "dictionary_candidate":d.get("describedBy")}

def number(raw):
    s=raw.strip()
    if norm(s) in MISSING:return None,"blank" if not s else "missing_token"
    if not re.fullmatch(r"[+-]?(?:[0-9]{1,25}(?:\.[0-9]{1,12})?|\.[0-9]{1,12})",s):
        return None,"unrecognized"
    try:n=Decimal(s)
    except InvalidOperation:return None,"unrecognized"
    return s,("zero" if n==0 else "negative" if n<0 else "positive")

def calendar(raw):
    s=raw.strip()
    if norm(s) in MISSING:return None,"blank" if not s else "missing_token"
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",s):
        try:return date.fromisoformat(s),"iso"
        except ValueError:return None,"invalid"
    m=re.fullmatch(r"([0-9]{1,2})/([0-9]{1,2})/([0-9]{4})",s)
    if not m:return None,"unrecognized"
    a,b,y=map(int,m.groups())
    def valid(month,day):
        try:return date(y,month,day)
        except ValueError:return None
    x,z=valid(a,b),valid(b,a)
    if x and z:return (x,"both_same") if x==z else (None,"ambiguous")
    if x:return x,"mdy_only"
    if z:return z,"dmy_only"
    return None,"invalid"

def project(data,expected,columns,api_fields,db,providers):
    reader=csv.DictReader(io.StringIO(data.decode("utf-8-sig"),newline=""),strict=True)
    header=reader.fieldnames or [];mapping={norm(h):h for h in header}
    needed=CORE+MEASURES
    require(len(header)==columns==len(mapping),"source column count/uniqueness")
    require(set(mapping)=={norm(h) for h in api_fields},"CSV and pinned API schema differ")
    require(all(norm(h) in mapping for h in needed),"required fields missing: "+", ".join(h for h in needed if norm(h) not in mapping))
    db.execute("""CREATE TABLE cost_report(
        report_key TEXT PRIMARY KEY,row_ordinal INTEGER NOT NULL,source_row_sha256 TEXT NOT NULL,
        ccn TEXT NOT NULL,state TEXT NOT NULL,begin_raw TEXT,end_raw TEXT,
        begin_state TEXT NOT NULL,end_state TEXT NOT NULL,link_state TEXT NOT NULL,measures_json TEXT NOT NULL)""")
    counts=defaultdict(Counter);dates=Counter();links=Counter();reject=Counter()
    seen=set();dup_rows=0;total=0;period_order=0;ccns=Counter()
    for total,row in enumerate(reader,1):
        require(total<=100000,"row limit")
        if None in row or any(v is None for v in row.values()):
            reject["malformed_width"]+=1;continue
        def get(h):return row[mapping[norm(h)]].strip()
        digest=hashlib.sha256(json.dumps(list(row.values()),ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        if digest in seen:dup_rows+=1
        seen.add(digest)
        key,ccn,state,begin,end=(get(h) for h in CORE)
        if not re.fullmatch(r"[0-9]{1,20}",key):
            reject["report_key_shape"]+=1;continue
        if not re.fullmatch(r"[A-Z0-9]{6}",ccn) or not re.fullmatch(r"[A-Z]{2}",state):
            reject["provider_key_shape"]+=1;continue
        a,ast=calendar(begin);b,bst=calendar(end)
        dates["begin_"+ast]+=1;dates["end_"+bst]+=1
        if a is not None and b is not None and b<a:period_order+=1
        link="same_state" if state in providers.get(ccn,set()) else "state_conflict" if ccn in providers else "unmatched_ccn"
        vals={};states={}
        for field in MEASURES:
            value,kind=number(get(field))
            vals[field]=value;states[field]=kind
        cursor=db.execute("INSERT OR IGNORE INTO cost_report VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                          (key,total,digest,ccn,state,begin,end,ast,bst,link,json.dumps(vals,separators=(",",":"))))
        if cursor.rowcount!=1:
            reject["duplicate_report_key"]+=1;continue
        for field,kind in states.items():counts[field][kind]+=1
        links[link]+=1;ccns[ccn]+=1
    db.commit();stored=db.execute("SELECT count(*) FROM cost_report").fetchone()[0]
    require(total==expected==stored+sum(reject.values()),"record reconciliation")
    require(stored==sum(links.values())==sum(ccns.values()),"link reconciliation")
    require(all(sum(counts[k].values())==stored for k in MEASURES),"measure reconciliation")
    db.execute("CREATE INDEX cost_report_ccn ON cost_report(ccn,state)")
    require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite integrity")
    sample=db.execute("SELECT ccn FROM cost_report LIMIT 1").fetchone()
    require(sample is not None and db.execute("SELECT count(*) FROM cost_report WHERE ccn=?",sample).fetchone()[0]>0,"populated lookup")
    return {"input_rows":total,"stored_rows":stored,"rejected_rows":sum(reject.values()),"reject_reasons":dict(reject),
            "exact_duplicate_rows":dup_rows,"distinct_ccns":len(ccns),"ccns_with_multiple_reports":sum(v>1 for v in ccns.values()),
            "link_counts":dict(links),"fiscal_date_shape_counts":dict(dates),"unambiguous_period_order_anomalies":period_order,
            "measure_value_states":{k:dict(counts[k]) for k in MEASURES},"columns":len(header),
            "projected_measure_count":len(MEASURES),"retained_row_level_records":0}

def main():
    p=argparse.ArgumentParser();p.add_argument("--cms-base",type=Path,required=True);p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    path=a.cms_base/"facilitysignal.sqlite3";require(not a.audit.exists() and sha(path)==BASE_SHA,"baseline or output mismatch")
    validate_base(a.cms_base)
    meta=select(registry.get_json(registry.CATALOG))
    count=registry.expected_rows(meta);require(0<count<=100000,"version API row count outside bound")
    sample=registry.get_json(meta["api"]+"?size=1")
    require(isinstance(sample,list) and len(sample)==1 and isinstance(sample[0],dict),"unexpected pinned API sample")
    require(len(CORE)<=len(sample[0])<=300,"version API column count outside bound")
    with registry.response(meta["url"],"text/csv") as res:
        registry.allowed(res.geturl());data=res.read(MAX_BYTES+1)
    require(0<len(data)<=MAX_BYTES,"source size bound")
    require(registry.expected_rows(meta)==count and select(registry.get_json(registry.CATALOG))==meta,"publisher changed during retrieval")
    providers={}
    with closing(readonly(path)) as src:
        for ccn,state in src.execute("SELECT ccn,state FROM facilities WHERE dataset='nursing'"):
            providers.setdefault(ccn,set()).add(state)
    with closing(sqlite3.connect(":memory:")) as db:
        audit=project(data,count,len(sample[0]),list(sample[0]),db,providers)
    require(sha(path)==BASE_SHA,"baseline mutated")
    audit.update({"publisher":meta,"source_sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data),
                  "retrieved_at":datetime.now(timezone.utc).isoformat(),"baseline_sha256":BASE_SHA,
                  "reuse_review":"pending","limits":"Report-scoped selected historical measures, not purchase intent, equipment count, vendor payments, current operating capacity or audited financial totals. No row-level publication, no sum across reporting periods, no ambiguous date normalization. Measure semantics and units require dictionary review."})
    a.audit.parent.mkdir(parents=True,exist_ok=True)
    with a.audit.open("x") as f:json.dump(audit,f,indent=2);f.write("\n")
    print("SNF_COST_AUDIT",json.dumps(audit),flush=True)
    require(audit["rejected_rows"]==audit["exact_duplicate_rows"]==audit["unambiguous_period_order_anomalies"]==0,"record anomalies require review")
    require(not any(x.get("unrecognized",0) for x in audit["measure_value_states"].values()),"numeric value anomalies require review")
    require(not any(v for k,v in audit["fiscal_date_shape_counts"].items() if k.endswith(("_invalid","_unrecognized"))),"date shape anomalies require review")

if __name__=="__main__":main()
