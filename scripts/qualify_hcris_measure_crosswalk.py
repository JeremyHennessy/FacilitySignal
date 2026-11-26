"""Read-only FY2024 direct-coordinate qualification against pinned selected PUFs."""
import argparse,csv,hashlib,io,json,os,sqlite3,tempfile
from collections import Counter,defaultdict
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from build_combined import require
import azure_national_archive as archive
import collect_registry as registry
from scripts import archive_hcris_large_numeric as large
from scripts import audit_azure_archive_inventory as inventory
from scripts import azure_source_archive as src, azure_verified_extension as ext
from scripts.qualify_hospital_cost import number,norm
ROOT=Path(__file__).resolve().parents[1]
# Explicit dictionary direct-cell candidates. Never infer composite measures.
MAPS={
 "hospital":{
 "Number of Beds":("S300001","01400","00200","bed_count"),
 "Total Salaries From Worksheet A":("A000000","20000","00100","monetary_source_value"),
 "Overhead Non-Salary Costs":("A000000","20000","00200","monetary_source_value"),
 "Depreciation Cost":("A700003","00300","00900","monetary_source_value"),
 "Total Costs":("C000001","20200","00300","monetary_source_value"),
 "Total Patient Revenue":("G300000","00100","00100","monetary_source_value"),
 "Net Patient Revenue":("G300000","00300","00100","monetary_source_value"),
 "Less Total Operating Expense":("G300000","00400","00100","monetary_source_value"),
 "Net Income":("G300000","02900","00100","monetary_source_value")},
 "snf":{
 "Number of Beds":("S300001","00800","00100","bed_count"),
 "Total Bed Days Available":("S300001","00800","00200","bed_days"),
 "Total Days Total":("S300001","00800","00700","days_or_visits_source_definition"),
 "Total Costs":("C000000","10000","00100","monetary_source_value"),
 "Total Charges":("C000000","10000","00200","monetary_source_value"),
 "Total Salaries From Worksheet A":("A000000","10000","00100","monetary_source_value"),
 "Overhead Non-Salary Costs":("A000000","10000","00200","monetary_source_value"),
 "Contract Labor":("S300002","01400","00300","monetary_source_value")}}
DICTIONARIES={
 "hospital":"https://data.cms.gov/sites/default/files/2024-03/9756088d-5280-4090-80b9-449d31ef25a3/Cost%20Report%20Data%20Dictionary%20Update.pdf",
 "snf":"https://data.cms.gov/sites/default/files/2023-12/Skilled%20Nursing%20Facility%20Cost%20Report%20Data%20Dictionary_508.pdf"}
def download(url,accept,limit):
    with registry.response(url,accept) as r:
        registry.allowed(r.geturl());require(r.geturl()==url,"pinned publisher URL changed");data=r.read(limit+1)
    require(0<len(data)<=limit,"publisher download bound");return data

def parse_puf(data,audit,mapping):
    require(len(data)==audit["bytes"] and hashlib.sha256(data).hexdigest()==audit["source_sha256"],"selected PUF exact byte pin")
    reader=csv.DictReader(io.StringIO(data.decode("utf-8-sig"),newline=""),strict=True)
    header=reader.fieldnames or [];fields={norm(k):k for k in header}
    require(len(header)==len(fields)==audit["columns"] and all(norm(k) in fields for k in ("rpt_rec_num",*mapping)),"PUF column scope")
    records={};states={name:Counter() for name in mapping}
    for row in reader:
        require(None not in row and all(v is not None for v in row.values()),"PUF width")
        key=row[fields["rpt_rec_num"]].strip()
        require(key.isascii() and key.isdecimal() and 1<=len(key)<=20 and key not in records,"PUF exact report key")
        record={}
        for name in mapping:
            v,s=number(row[fields[norm(name)]]);states[name][s]+=1
            require(s!="unrecognized","PUF numeric syntax")
            record[name]=(None if v is None else Decimal(v),s)
        records[key]=record
    require(len(records)==audit["stored_rows"]==audit["input_rows"],"PUF row count")
    require(all(dict(states[n])==audit["measure_value_states"][n] for n in mapping),"PUF prior measure state drift")
    return records

def load_db(store,pin,national,path):
    name=src.prefix_for(pin["key"],pin["source_sha256"])+"/complete.json"
    rec,digest,head=ext.read_small(store,name);inventory.source_matches(rec,pin,national)
    dbpin=next(f for f in pin["files"] if f["path"]=="projection.sqlite3")
    ext.fetch_verified(store,rec["payload_prefix"]+"/projection.sqlite3",dbpin,path)
    require(ext.read_small(store,name,digest)[2]==head,"receipt changed during download")
    return rec

def ro(path):
    return sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)

def read_parents(path,expected):
    with closing(ro(path)) as db:
        cols={r[1] for r in db.execute("PRAGMA table_info(reports)")}
        require({"report_key","numeric_rows"}<=cols,"report index schema")
        if "source_year" in cols:
            require(db.execute("SELECT DISTINCT source_year FROM reports").fetchall()==[("2024",)],"report year scope")
        parents=dict(db.execute("SELECT report_key,numeric_rows FROM reports"))
    require(len(parents)==expected and all(isinstance(n,int) and n>=0 for n in parents.values()),"parent report count")
    return parents

def extract(path,pin,parents,mapping,found):
    coords={v[:3]:name for name,v in mapping.items()};require(len(coords)==len(mapping),"unique measure coordinates")
    clauses=" OR ".join("(worksheet=? AND line=? AND col=?)" for _ in coords)
    args=[v for c in coords for v in c];counts=Counter()
    with closing(ro(path)) as db:
        count,lo,hi,years=db.execute("SELECT count(*),min(ordinal),max(ordinal),count(DISTINCT source_year) FROM numeric_cells").fetchone()
        require(count==pin["observations"] and pin["ordinal_start"]<=lo<=hi<=pin["ordinal_end"] and years==1,"numeric shard counts/ranges")
        require(db.execute("SELECT DISTINCT source_year FROM numeric_cells").fetchall()==[("2024",)],"numeric year")
        for key,w,l,c,raw,ordinal in db.execute("SELECT report_key,worksheet,line,col,value_text,ordinal FROM numeric_cells WHERE "+clauses,args):
            require(key in parents and pin["ordinal_start"]<=ordinal<=pin["ordinal_end"],"numeric parent/ordinal scope")
            name=coords[(w,l,c)];v,state=number(raw)
            require(state!="unrecognized","archived numeric syntax")
            found[name][key].append((None if v is None else Decimal(v),state));counts[name]+=1
    return counts

def compare(mapping,parents,records,found):
    overlap=set(parents)&set(records);result={}
    for name,coord in mapping.items():
        cells=found[name];counts=Counter();duplicates=sum(len(v)>1 for v in cells.values())
        for key in overlap:
            pv,ps=records[key][name];av=cells.get(key,[])
            if len(av)>1:counts["ambiguous_multiple_cells"]+=1;continue
            if not av:counts["puf_missing_archive_absent" if pv is None else "puf_numeric_archive_absent"]+=1;continue
            val,st=av[0]
            if pv is None and val is None:counts["both_explicit_missing"]+=1
            elif pv is None:counts["puf_missing_archive_explicit_zero" if val==0 else "puf_missing_archive_numeric"]+=1
            elif val is None:counts["puf_numeric_archive_explicit_missing"]+=1
            else:counts["equal_decimal" if pv==val else "unequal_decimal"]+=1
        require(sum(counts.values())==len(overlap),"comparison accounting")
        complete=counts["equal_decimal"]>0 and counts["unequal_decimal"]==counts["puf_numeric_archive_absent"]==counts["puf_numeric_archive_explicit_missing"]==counts["puf_missing_archive_numeric"]==counts["ambiguous_multiple_cells"]==0
        result[name]={"coordinate":list(coord[:3]),"unit_candidate":coord[3],"archive_coordinate_rows":sum(map(len,cells.values())),"archive_report_keys_with_coordinate":len(cells),"archive_duplicate_coordinate_report_keys":duplicates,"comparisons":dict(sorted(counts.items())),"qualification":"matched_report_parity_supported" if complete else "review_required"}
    return {"report_key_intersection":len(overlap),"archive_only_report_keys":len(set(parents)-overlap),"puf_only_report_keys":len(set(records)-overlap),"measures":result}

def run(form,store,root):
    ledger=json.loads(inventory.LEDGER.read_text());inventory.totals(ledger)
    cov=json.loads((ROOT/"research/coverage_status.json").read_text());audit=cov[form+"_cost_qualified_baseline"]["audit"]
    require(audit["publisher"]["dictionary_candidate"]==DICTIONARIES[form],"dictionary catalog link")
    doc=download(DICTIONARIES[form],"application/pdf",10_000_000);require(doc.startswith(b"%PDF-"),"publisher dictionary PDF")
    records=parse_puf(download(audit["publisher"]["url"],"text/csv",audit["bytes"]),audit,MAPS[form])
    national=ext.national_manifest(store)
    parent=next(x for x in ledger["receipts"] if x["key"]==f"hcris-{form}-2024-index" and x["kind"]=="publisher")
    path=root/"parent.sqlite3";load_db(store,parent,national,path);parents=read_parents(path,parent["observations"]);path.unlink()
    require(sum(parents.values())==src.LARGE_NUMERIC_ROWS[form],"parent numeric total")
    wanted={key for key,(f,_,_) in src.LARGE_NUMERIC_SCOPES.items() if f==form}
    pins=[x for x in ledger["receipts"] if x["key"] in wanted and x["source_sha256"]==parent["source_sha256"]]
    require(len(pins)==len(wanted) and {x["key"] for x in pins}==wanted,"complete shard pin set")
    found={name:defaultdict(list) for name in MAPS[form]};counts=Counter();excluded=Counter();observations=0
    for i,pin in enumerate(sorted(pins,key=lambda x:x["ordinal_start"])):
        require(pin["kind"]=="supplemental_numeric","numeric archive grain")
        path=root/("shard-"+str(i)+".sqlite3");rec=load_db(store,pin,national,path)
        counts.update(extract(path,pin,parents,MAPS[form],found));path.unlink();observations+=pin["observations"]
        for key in ("unresolved_parent_rows","coordinate_review_rows","numeric_syntax_review_rows"):excluded[key]+=rec["summary"][key]
    require(observations+sum(excluded.values())==sum(parents.values()),"whole numeric member accounting")
    require(all(counts[n]==sum(map(len,found[n].values())) for n in MAPS[form]),"coordinate count reconciliation")
    ext.unchanged(store,national)
    return {"status":"COMPLETE","form":form,"archive_source_sha256":parent["source_sha256"],"puf_sha256":audit["source_sha256"],"dictionary_url":DICTIONARIES[form],"dictionary_sha256":hashlib.sha256(doc).hexdigest(),"archive_reports":len(parents),"puf_reports":len(records),"numeric_shards":len(pins),"verified_archived_numeric_rows":observations,"excluded_source_rows":dict(excluded),**compare(MAPS[form],parents,records,found),"monetary_scale_qualified":False,"report_cutoffs_assumed_equal":False,"facility_financial_attribution":False,"individual_values_retained":False,"azure_writes":0,"public_promotion":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--form",choices=MAPS,required=True);p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");archive.run_key(os.environ)
    store=inventory.ReadOnlyAzure(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="hcris-measure-") as d:result=run(args.form,store,Path(d))
    finally:store.close()
    args.receipt.write_bytes(archive.encode(result))
    print("HCRIS_MEASURE_CROSSWALK_COMPLETE",json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":main()
