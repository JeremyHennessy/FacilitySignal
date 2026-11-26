"""Source-scoped institutional observations, qualified in an ephemeral SQLite candidate.

No public row-level payload, production schema change, or physical-site merge.
"""
import argparse,json,sqlite3,tempfile
from collections import Counter
from pathlib import Path
from restore_snapshot import LOCK,load_lock,materialize
from qualified_data_use import source_rows,compare_directory,sha,ROOT,read,need
YES_NO={"Yes":"reported_yes","No":"reported_no"}
YN={"Y":"reported_yes","N":"reported_no"}
RULES={
 "hospital":{
   "emergency_services":("Emergency Services",YES_NO,"Reported emergency services, not live availability")},
 "dialysis":{
   "chain_owned_or_managed":("Chain Owned",YES_NO,"Source-reported chain ownership or management, not legal title"),
   "late_shift":("Late Shift",YES_NO,"Reported shift starting at 17:00 or later"),
   "in_center_hemodialysis":("Offers in-center hemodialysis",YES_NO,"Source-reported treatment service"),
   "peritoneal_dialysis":("Offers peritoneal dialysis",YES_NO,"Source-reported treatment service"),
   "home_hemodialysis_training":("Offers home hemodialysis training",YES_NO,"Source-reported training service")},
 "nursing":{
   "sprinklers":("Automatic Sprinkler Systems in All Required Areas",{"Yes":"all_required_areas","Partial":"partial","Data Not Available":"not_available"},"Reported sprinkler coverage, not independently inspected condition"),
   "health_survey_over_two_years":("Most Recent Health Inspection More Than 2 Years Ago",YN,"Reported survey-age flag, not proof of an overdue legal requirement"),
   "ownership_change_12_months":("Provider Changed Ownership in Last 12 Months",YN,"Reported change flag, not a deed"),
   "special_focus":("Special Focus Status",{"SFF":"reported_sff","SFF Candidate":"reported_candidate","":"not_reported"},"Reported oversight status; blank is not negative")}
}
DDL="""
CREATE TABLE candidate_release (
 source TEXT PRIMARY KEY, release TEXT NOT NULL, source_sha256 TEXT NOT NULL,
 directory_sha256 TEXT NOT NULL, provider_count INTEGER NOT NULL CHECK(provider_count>0));
CREATE TABLE candidate_provider (
 source TEXT NOT NULL, ccn TEXT NOT NULL, state TEXT NOT NULL,
 PRIMARY KEY(source,ccn,state), FOREIGN KEY(source) REFERENCES candidate_release(source));
CREATE TABLE candidate_field (
 source TEXT NOT NULL, field TEXT NOT NULL, raw_header TEXT NOT NULL,
 meaning TEXT NOT NULL, domain_json TEXT NOT NULL,
 PRIMARY KEY(source,field), FOREIGN KEY(source) REFERENCES candidate_release(source));
CREATE TABLE candidate_observation (
 source TEXT NOT NULL, ccn TEXT NOT NULL, state TEXT NOT NULL, field TEXT NOT NULL,
 value_state TEXT NOT NULL,
 PRIMARY KEY(source,ccn,state,field),
 FOREIGN KEY(source,ccn,state) REFERENCES candidate_provider(source,ccn,state),
 FOREIGN KEY(source,field) REFERENCES candidate_field(source,field));
CREATE INDEX candidate_filter ON candidate_observation(source,field,value_state,state);
"""
def observation(field,raw):
    _,domain,_=field
    need(raw in domain,"unexpected source value; no guessed category")
    return domain[raw]
def setup(db):
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(DDL)
def add_source(db,key,pin,rows,directory_digest):
    rules=RULES[key]
    with db:
        db.execute("INSERT INTO candidate_release VALUES(?,?,?,?,?)",(key,pin["release"],pin["sha256"],directory_digest,len(rows)))
        for field,(header,domain,meaning) in rules.items():
            db.execute("INSERT INTO candidate_field VALUES(?,?,?,?,?)",(key,field,header,meaning,json.dumps(domain,sort_keys=True)))
        for (ccn,state),(raw,identity) in rows.items():
            need(identity["ccn"]==ccn and identity["state"]==state and bool(ccn) and bool(state),"source identity discrepancy")
            db.execute("INSERT INTO candidate_provider VALUES(?,?,?)",(key,ccn,state))
            db.executemany("INSERT INTO candidate_observation VALUES(?,?,?,?,?)",
                ((key,ccn,state,field,observation(rule,raw[rule[0]])) for field,rule in rules.items()))
        need(db.execute("SELECT count(*) FROM candidate_observation WHERE source=?",(key,)).fetchone()[0]==len(rows)*len(rules),"observation count mismatch")
def filters(db,source,field,value_state,state=None):
    need(source in RULES and field in RULES[source] and value_state in RULES[source][field][1].values(),"unsupported source-scoped filter")
    sql="SELECT ccn,state FROM candidate_observation WHERE source=? AND field=? AND value_state=?"
    args=[source,field,value_state]
    if state is not None:sql+=" AND state=?";args.append(state)
    return db.execute(sql+" ORDER BY state,ccn",args).fetchall()
def validate(db,key,rows,expected):
    counts={}
    for field,rule in RULES[key].items():
        header,domain,_=rule
        raw_counts=expected[header]
        need(set(raw_counts)<=set(domain),"prior literal domain differs")
        wanted=Counter()
        for raw,n in raw_counts.items():wanted[domain[raw]]+=n
        wanted={k:v for k,v in wanted.items() if v}
        actual=dict(db.execute("SELECT value_state,count(*) FROM candidate_observation WHERE source=? AND field=? GROUP BY value_state",(key,field)))
        need(actual==wanted and sum(actual.values())==len(rows),"prior aggregate mismatch: "+field)
        for value,n in actual.items():
            hits=filters(db,key,field,value)
            need(len(hits)==n and len(set(hits))==n,"filter mismatch")
            direct={pair for pair,(raw,_) in rows.items() if observation(rule,raw[header])==value}
            need(set(hits)==direct,"filter membership mismatch")
            by_state=Counter(s for _,s in hits)
            for state,k in by_state.items():need(len(filters(db,key,field,value,state))==k,"state filter mismatch")
        counts[field]=actual
    return counts
def main():
    p=argparse.ArgumentParser();p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    pins={s["key"]:s for s in load_lock(LOCK)["sources"]}
    headers={s["source"]:s for s in read(ROOT/"research/care_compare_pecos_exact_headers_20261126.json")["sources"]}
    prior=read(ROOT/"research/care_compare_infrastructure_qualification_20261126.json")
    need(prior["qualification_run"]==45835796014 and prior["tests_passed"]==4,"prior qualification mismatch")
    prof=read(ROOT/"research/care_compare_directory_raw_field_profiles_20261126.json")
    hp=next(s for s in prof["sources"] if s["source"]=="hospital")
    hf=next(f for f in hp["fields"] if f["field"]=="Emergency Services")
    need(hp["source_sha256"]==pins["hospital"]["sha256"],"hospital profile drift")
    hc=hf["literal_yes_no_counts"];need(hc=={"yes":4501,"no":934},"hospital emergency profile drift")
    market=read(ROOT/"web/market-summary.json")["sources"]
    out={}
    with sqlite3.connect(":memory:") as db:
        setup(db)
        for key,rules in RULES.items():
            pin=pins[key];h=headers[key]
            need(h["source_sha256"]==pin["sha256"],"header pin drift")
            directory=ROOT/"web/public-directory"/(key+".json")
            digest=sha(directory);need(digest==market[key]["sha256"],"public directory hash drift")
            if key=="hospital":expected={"Emergency Services":{"Yes":hc["yes"],"No":hc["no"]}}
            else:
                pr=prior["sources"][key];need(pr["sha256"]==pin["sha256"] and pr["rows"]==pin["stored_rows"],"prior source drift")
                expected={f:{("" if v=="<blank>" else v):n for v,n in c.items()} for f,c in pr["literal_counts"].items()}
            with tempfile.TemporaryDirectory() as d:
                raw=materialize(pin,a.raw_dir,Path(d),a.download)
                rows=source_rows(raw,pin,[f["field"] for f in h["fields"]])
                compare_directory(read(directory),pin,rows)
                add_source(db,key,pin,rows,digest)
                counts=validate(db,key,rows,expected)
            out[key]={"source_sha256":pin["sha256"],"release":pin["release"],"public_sha256":digest,"providers":len(rows),"observations":len(rows)*len(rules),"fields":counts}
        need(db.execute("PRAGMA integrity_check").fetchall()==[("ok",)] and not db.execute("PRAGMA foreign_key_check").fetchall(),"SQLite integrity failed")
        n=db.execute("SELECT count(*) FROM candidate_observation").fetchone()[0]
        need(n==sum(v["observations"] for v in out.values()),"national observation total drift")
    evidence={"sources":out,"source_records":sum(x["providers"] for x in out.values()),"observations":n,"field_rules":sum(len(r) for r in RULES.values()),"sqlite_integrity":"ok","membership_and_state_filter_checks":"passed","limits":"Ephemeral institutional candidate only. Exact same-source public directory and raw identities; no new public individual evidence, canonical property, current operation or compliance inference."}
    with a.output.open("x") as f:json.dump(evidence,f,indent=2,sort_keys=True)
    print("INSTITUTIONAL_OBSERVATIONS",json.dumps(evidence,sort_keys=True))
if __name__=="__main__":main()
