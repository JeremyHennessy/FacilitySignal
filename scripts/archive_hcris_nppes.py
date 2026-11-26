"""Archive qualified HCRIS cells and NPPES institutional records privately.

HCRIS: retain report keys, exact numeric values and coordinate-level alpha
presence only. No unreviewed alpha text or report header metadata.
NPPES: Type 2 NPIs, report date/region/taxonomy observations, no names, addresses,
contacts, Type 1 identifiers, endpoint contents, or inferred active status.
Each publisher release remains independent; no weekly union or dedup across weeks.
"""
import argparse,csv,io,json,os,re,sqlite3,tempfile,zipfile
from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path
import azure_national_archive as a
from build_combined import require,sha,readonly,check_integrity
from scripts import azure_source_archive as storage,qualify_hcris_hha as h,qualify_nppes_v2 as n
ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"research/coverage_status.json"

def verify_source(meta,pin,path):
    require(all(meta[k]==pin[k] for k in ("url","bytes","sha256")) and sha(path)==pin["sha256"] and path.stat().st_size==pin["bytes"],"publisher release bytes changed")

def hcris_project(path,db,prior):
    # Preserve all source ordinals; repeated coordinates are observations,
    # never silently discarded or interpreted as conflicting values.
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""CREATE TABLE reports(report_key TEXT PRIMARY KEY,ordinal INTEGER NOT NULL UNIQUE);
    CREATE TABLE numeric_cells(ordinal INTEGER PRIMARY KEY,report_key TEXT NOT NULL REFERENCES reports(report_key),worksheet TEXT NOT NULL,line TEXT NOT NULL,col TEXT NOT NULL,value_text TEXT NOT NULL,value_state TEXT NOT NULL);
    CREATE TABLE alpha_coordinates(ordinal INTEGER PRIMARY KEY,report_key TEXT NOT NULL REFERENCES reports(report_key),worksheet TEXT NOT NULL,line TEXT NOT NULL,col TEXT NOT NULL,value_state TEXT NOT NULL);""")
    result={}
    with zipfile.ZipFile(path) as z:
        roles=h.members(z)
        for role,info in roles.items():
            require(info.file_size==prior[role]["uncompressed_bytes"] and format(info.CRC,"08x")==prior[role]["zip_crc32"],"member identity differs")
        with z.open(roles["report"]) as raw,io.TextIOWrapper(raw,encoding="latin-1",newline="") as f:
            keys=set()
            for ordinal,row in enumerate(csv.reader(f,strict=True),1):
                require(ordinal<=100000 and len(row)==18,"report row shape")
                key=h.report_key(row[0]);require(key is not None and key not in keys,"report key")
                keys.add(key);db.execute("INSERT INTO reports VALUES(?,?)",(key,ordinal))
            require(len(keys)==prior["report"]["rows"],"report count")
            result["report_rows"]=len(keys)
        for role,table in (("numeric","numeric_cells"),("alpha","alpha_coordinates")):
            counts=Counter();classes=Counter();batch=[];total=0;coordinates=set();covered=set()
            with z.open(roles[role]) as raw,io.TextIOWrapper(raw,encoding="latin-1",newline="") as f:
                for total,row in enumerate(csv.reader(f,strict=True),1):
                    require(total<=h.MAX_ROWS and len(row)==5,"cell row shape")
                    key=h.report_key(row[0]);require(key in keys,"orphan report")
                    worksheet,line,col=(x.strip() for x in row[1:4]);kind=h.coordinate_class(worksheet,line,col,role)
                    require(kind!="unrecognized","coordinate shape")
                    state=h.cell_state(row[4]) if role=="numeric" else ("present" if row[4].strip() else "blank")
                    require(state!="unrecognized","numeric cell syntax")
                    counts[state]+=1;classes[kind]+=1;coordinates.add((worksheet,line,col));covered.add(key)
                    batch.append((total,key,worksheet,line,col,row[4].strip(),state) if role=="numeric" else (total,key,worksheet,line,col,state))
                    if len(batch)>=10000:
                        db.executemany("INSERT INTO "+table+" VALUES("+",".join("?" for _ in batch[0])+")",batch);batch.clear()
                if batch:db.executemany("INSERT INTO "+table+" VALUES("+",".join("?" for _ in batch[0])+")",batch)
            expected=prior[role]
            require(total==expected["rows"] and dict(counts)==expected["value_states"] and dict(classes)==expected["coordinate_class_counts"] and len(covered)==expected["reports_with_cells"] and len(coordinates)==expected["distinct_valid_worksheet_coordinates"],"prior cell audit mismatch")
            db.execute("CREATE INDEX "+table+"_report_coordinate ON "+table+"(report_key,worksheet,line,col)")
            duplicate=db.execute("SELECT coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM "+table+" GROUP BY report_key,worksheet,line,col HAVING n>1)").fetchone()[0]
            require(db.execute("SELECT count(*) FROM "+table).fetchone()[0]==total,"stored cell count")
            result[role+"_rows"]=total;result[role+"_repeated_coordinate_rows"]=duplicate
        db.commit();check_integrity(db)
    return {**result,"alpha_values_retained":0,"report_metadata_fields_retained":["report_key","ordinal"],"numeric_values_retained":result["numeric_rows"],"source_observations":sum(result[x] for x in ("report_rows","numeric_rows","alpha_rows")),"units_interpreted":False}

def normalize_date(v):
    state=n.date_state(v)
    return datetime.strptime(v.strip(),"%m/%d/%Y").date().isoformat() if state=="reported" else None

class OrgObserver:
    def __init__(self):self.ready=False;self.batch=[];self.tax=[];self.states=Counter();self.seen=0
    def finish(self,db):self.flush(db)
    def flush(self,db):
        if self.batch:db.executemany("INSERT INTO organization_fields VALUES(?,?,?,?,?,?,?,?)",self.batch);self.batch.clear()
        if self.tax:db.executemany("INSERT INTO organization_taxonomy VALUES(?,?,?)",self.tax);self.tax.clear()
    def __call__(self,db,npi,ordinal,get,tax):
        if not self.ready:
            db.executescript("""CREATE TABLE organization_fields(npi TEXT PRIMARY KEY,ordinal INTEGER NOT NULL UNIQUE,enumerated_on TEXT,updated_on TEXT,deactivated_on TEXT,reactivated_on TEXT,practice_state TEXT,practice_country TEXT) WITHOUT ROWID;
            CREATE TABLE organization_taxonomy(npi TEXT NOT NULL,slot INTEGER NOT NULL,code TEXT NOT NULL,PRIMARY KEY(npi,slot)) WITHOUT ROWID;""")
            self.ready=True
        self.seen+=1
        dates=[normalize_date(get(k)) for k in ("Provider Enumeration Date","Last Update Date","NPI Deactivation Date","NPI Reactivation Date")]
        state=get("Provider Business Practice Location Address State Name").strip().upper()
        country=get("Provider Business Practice Location Address Country Code (If outside U.S.)").strip().upper()
        if state and not re.fullmatch(r"[A-Z]{2}",state):self.states["state_unrecognized"]+=1;state=None
        if country and not re.fullmatch(r"[A-Z]{2}",country):self.states["country_unrecognized"]+=1;country=None
        self.batch.append((npi,ordinal,*dates,state or None,country or None))
        for i,raw in enumerate(tax,1):
            code=raw.strip().upper()
            if not code:continue
            if not re.fullmatch(r"[A-Z0-9]{10}",code):self.states["taxonomy_unrecognized"]+=1;continue
            self.tax.append((npi,i,code));self.states["taxonomy_retained"]+=1
        if len(self.batch)>=10000:self.flush(db)

def nppes_project(path,db_path,kind,prior=None):
    observer=OrgObserver()
    audit=n.inspect(path,db_path,kind,organization_observer=observer)
    if prior is not None:require(all(audit[k]==prior[k] for k in audit),"NPPES original structural audit differs")
    expected=audit["distinct_valid_organization_npis"]
    c=audit["entity_classes"];k=audit["organization_key_counts"]
    require(expected>0 and not any(c.get(x,0) for x in ("malformed_width","unrecognized_entity_type")) and k.get("invalid_organization_npi",0)==audit["duplicate_valid_organization_rows"]==0,"organization exceptions")
    require(all(not x["key_counts"].get("malformed_width") and not x["key_counts"].get("invalid_key_shape") for x in audit["reference_files"].values()),"reference exceptions")
    require(observer.seen==expected and not observer.batch and not observer.tax,"observer reconciliation")
    with closing(sqlite3.connect(db_path)) as db:
        require(db.execute("SELECT count(*) FROM organizations").fetchone()[0]==db.execute("SELECT count(*) FROM organization_fields").fetchone()[0]==expected,"organization table count")
        require(not db.execute("SELECT 1 FROM organization_fields f LEFT JOIN organizations o ON o.npi=f.npi WHERE o.npi IS NULL LIMIT 1").fetchone(),"organization detail orphan")
        require(not db.execute("SELECT 1 FROM organization_taxonomy t LEFT JOIN organizations o ON o.npi=t.npi WHERE o.npi IS NULL LIMIT 1").fetchone(),"taxonomy orphan")
        taxonomy=db.execute("SELECT count(*) FROM organization_taxonomy").fetchone()[0]
        require(taxonomy==observer.states["taxonomy_retained"],"taxonomy count")
        db.execute("CREATE INDEX org_state ON organization_fields(practice_state)")
        db.execute("CREATE INDEX org_taxonomy_code ON organization_taxonomy(code)")
        db.commit();check_integrity(db)
    return {"input_rows":audit["input_rows"],"organization_observations":expected,"individual_rows_excluded":audit["entity_classes"].get("individual_excluded",0),"untyped_rows_excluded":sum(v for k,v in audit["entity_classes"].items() if k.startswith("untyped_")),"taxonomy_observations":taxonomy,"field_shape_exceptions":dict(observer.states),"organization_names_addresses_contacts_retained":0,"individual_identifiers_retained":0,"reference_membership_counts":{k:v["key_counts"] for k,v in audit["reference_files"].items()},"weekly_applied_to_monthly":False,"structural_audit":audit}

def run_one(store,national,key,prior,root):
    meta=prior["audit"]["publisher"];kind="hcris-hha-2024" if key=="hcris" else "nppes-monthly" if key=="monthly" else "nppes-weekly"
    found=storage.existing(store,kind,meta["sha256"])
    if found:return found
    with tempfile.TemporaryDirectory(prefix="institutional-source-",dir=root) as d:
        stage=Path(d);source=stage/"source.zip";db_path=stage/"projection.sqlite3"
        if key=="hcris":
            observed=h.download(source);verify_source(observed,meta,source)
            with closing(sqlite3.connect(db_path)) as db:summary=hcris_project(source,db,prior["audit"]["tables"])
        else:
            observed=n.download(source,"monthly" if key=="monthly" else "weekly",publisher_label=prior["audit"]["publisher_label"])
            verify_source(observed,meta,source)
            summary=nppes_project(source,db_path,"monthly" if key=="monthly" else "weekly",prior["audit"])
        source.unlink()
        audit={"source_key":key,"publisher":meta,"prior_qualification_run":prior["run"],"summary":summary,"projection_sha256":sha(db_path),"projection_bytes":db_path.stat().st_size,"reuse_review":"pending","public_promotion":False}
        return storage.publish(store,kind,meta,db_path,audit,stage,national)

def main():
    p=argparse.ArgumentParser();p.add_argument("--source",choices=("hcris","monthly","weekly"),required=True);p.add_argument("--receipt",type=Path,required=True);args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists")
    a.run_key(os.environ);store=storage.SourceAzure(os.environ)
    try:
        national=storage.national_manifest(store);ledger=json.loads(LEDGER.read_text())
        pins={"hcris":ledger["hcris_hha_structural_baseline"],**ledger["nppes_v2_qualified_baselines"]}
        keys=["week_1102","week_1109","weekly"] if args.source=="weekly" else [args.source]
        results={}
        with tempfile.TemporaryDirectory(prefix="institutional-archive-") as d:
            for key in keys:
                results[key]=run_one(store,national,key,pins[key],Path(d))
                print("PRIVATE_INSTITUTIONAL_SOURCE_COMPLETE",key,json.dumps(results[key],sort_keys=True),flush=True)
        args.receipt.write_bytes(a.encode(results))
    finally:store.close()
if __name__=="__main__":main()
