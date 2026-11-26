"""Qualify PECOS organization roles, ownership flags, enrollment identity and CHOW.

Only aggregate counts are retained. Individuals are skipped before inspecting
their fields. No inferred legal ownership, current portfolio, or procurement.
"""
import argparse,csv,json,re,tempfile
from collections import Counter,defaultdict
from datetime import date,datetime
from decimal import Decimal
from pathlib import Path
from collect_registry import source_encoding,open_csv
from restore_snapshot import materialize,verify_raw
from pos_raw_field_profile import read,need,LOCK
ROOT=Path(__file__).resolve().parent
HEADERS=ROOT/"research/care_compare_pecos_exact_headers_20261126.json"
AS_OF=date(2026,11,26)
COMMON={"01":"5% OR MORE OWNERSHIP INTEREST","03":"PARTNER","25":"CONTRACTED MANAGING EMPLOYEE",
"34":"5% OR GREATER DIRECT OWNERSHIP INTEREST","35":"5% OR GREATER INDIRECT OWNERSHIP INTEREST",
"36":"5% OR GREATER MORTGAGE INTEREST","37":"5% OR GREATER SECURITY INTEREST",
"38":"GENERAL PARTNERSHIP INTEREST","39":"LIMITED PARTNERSHIP INTEREST","40":"OFFICER",
"41":"DIRECTOR","42":"W-2 MANAGING EMPLOYEE","43":"OPERATIONAL/MANAGERIAL CONTROL","44":"OTHER"}
ROLES={"hospital":COMMON,"snf":{**COMMON,"63":"MANAGING CONTROL – GOVERNING BODY","71":"TRUSTEE OF THE SNF",
"72":"ADP OF THE SNF","85":"DIRECT OWNERSHIP INTEREST","86":"INDIRECT OWNERSHIP INTEREST"}}
CLASSES={"01":"ownership_unspecified","34":"direct_ownership","35":"indirect_ownership","85":"direct_ownership",
"86":"indirect_ownership","03":"partnership","38":"partnership","39":"partnership","36":"financial_interest",
"37":"financial_interest","25":"management","42":"management","43":"management","40":"governance",
"41":"governance","63":"governance","71":"trustee","72":"additional_disclosable_party","44":"other"}
FLAGS=("CREATED FOR ACQUISITION","CORPORATION","LLC","MEDICAL PROVIDER SUPPLIER",
"MANAGEMENT SERVICES COMPANY","MEDICAL STAFFING COMPANY","HOLDING COMPANY","INVESTMENT FIRM",
"FINANCIAL INSTITUTION","CONSULTING FIRM","FOR PROFIT","NON PROFIT","PRIVATE EQUITY COMPANY",
"REIT","CHAIN HOME OFFICE","OTHER TYPE","OWNED BY ANOTHER ORG OR IND")
FLAGS_BY={"hospital":FLAGS,"snf":FLAGS+("TRUST OR TRUSTEE","PARENT COMPANY")}
CHOW={"AM":"ACQUISITION/MERGER","CH":"CHANGE OF OWNERSHIP (CHOW)","CO":"CONSOLIDATION"}
DOCS={k:"https://data.cms.gov/sites/default/files/2026-07/"+v+".pdf" for k,v in {
"hospital-owner":"Hospital_All_Owners_Data_Dictionary","snf-owner":"SNF_All_Owners_Data_Dictionary",
"hospital-enrollment":"Hospital_Enrollments_Data_Dictionary","snf-enrollment":"SNF_Enrollments_Data_Dictionary",
"hospital-chow":"Hospital_CHOW_Data_Dictionary","snf-chow":"SNF_CHOW_Data_Dictionary",
"snf-guidance":"SNF_Data_Guidance"}.items()}
def normalized(s):
    return " ".join(s.replace("–","-").replace("—","-").upper().split())
def flag(s):
    return {"Y":"yes","N":"no","":"blank"}.get(s.strip(),"unrecognized")
def key(value,pattern):
    v=value.strip()
    return v if re.fullmatch(pattern,v) else None
def pair(row,suffix=""):
    e=key(row["ENROLLMENT ID"+suffix],r"[A-Za-z0-9]{15}")
    p=key(row["ASSOCIATE ID"+suffix],r"[0-9]{10}")
    return (e,p) if e and p else None
def value_state(value,pattern):
    return "blank" if not value.strip() else "valid" if key(value,pattern) else "nonstandard"
def role(row,family):
    c=row["ROLE CODE - OWNER"].strip()
    t=normalized(row["ROLE TEXT - OWNER"])
    if not c:return "blank","unresolved","blank_code"
    if c not in ROLES[family]:return "unrecognized","unresolved","unknown_code"
    state="matches" if t==normalized(ROLES[family][c]) else "blank_text" if not t else "text_differs"
    return c,CLASSES[c] if state=="matches" else "unresolved",state
def percentage(value):
    s=value.strip()
    if not s:return "blank",None
    if len(s)>30 or not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?",s):return "unrecognized",None
    n=Decimal(s)
    if n<0 or n>100:return "outside_0_100",None
    return ("zero" if n==0 else "positive_below_5" if n<5 else "5_to_below_100" if n<100 else "100"),n
def date_state(value):
    s=value.strip()
    if not s:return "blank",None
    for fmt in ("%Y-%m-%d","%Y%m%d"):
        try:
            d=datetime.strptime(s,fmt).date()
            if d.strftime(fmt)!=s:continue
            return "parsed_"+("future" if d>AS_OF else "as_of_or_before"),d
        except ValueError:pass
    if re.fullmatch(r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}",s):
        ds=set()
        for fmt in ("%m/%d/%Y","%d/%m/%Y"):
            try:ds.add(datetime.strptime(s,fmt).date())
            except ValueError:pass
        if len(ds)>1:return "ambiguous_slash",None
        if ds:
            d=ds.pop()
            return "parsed_"+("future" if d>AS_OF else "as_of_or_before"),d
    return "unrecognized",None
def rows(path,pin,header):
    verify_raw(path,pin)
    enc=source_encoding(path,pin["metadata"]["zipped"]);n=0
    with open_csv(path,pin["metadata"]["zipped"],enc) as f:
        reader=csv.DictReader(f);need(reader.fieldnames==header,"exact pinned source header")
        for row in reader:
            need(None not in row and all(v is not None for v in row.values()),"malformed source row")
            n+=1;yield row
    need(n==pin["input_rows"],"raw source count mismatch");verify_raw(path,pin)
def memberships(n):
    return "1" if n==1 else "2-4" if n<=4 else "5-19" if n<=19 else "20-99" if n<=99 else "100+"
def enrollment_audit(stream):
    counts=Counter();ids=defaultdict(list);pacs=defaultdict(set);npis=defaultdict(set)
    kinds={f:Counter() for f in ("ENROLLMENT ID","ASSOCIATE ID","CCN","NPI","MULTIPLE NPI FLAG","PROPRIETARY NONPROFIT","INCORPORATION DATE")}
    for r in stream:
        counts["rows"]+=1
        p=pair(r)
        for f,pat in (("ENROLLMENT ID",r"[A-Za-z0-9]{15}"),("ASSOCIATE ID",r"[0-9]{10}"),("CCN",r"[A-Za-z0-9]{6}"),("NPI",r"[0-9]{10}")):
            kinds[f][value_state(r[f],pat)]+=1
        kinds["MULTIPLE NPI FLAG"][flag(r["MULTIPLE NPI FLAG"])]+=1
        kinds["PROPRIETARY NONPROFIT"][{"P":"proprietary","N":"nonprofit","":"blank"}.get(r["PROPRIETARY NONPROFIT"].strip(),"unrecognized")]+=1
        kinds["INCORPORATION DATE"][date_state(r["INCORPORATION DATE"])[0]]+=1
        if not p:counts["invalid_or_missing_enrollment_pac"]+=1;continue
        counts["valid_enrollment_pac"]+=1
        ids[p].append((r["CCN"].strip(),r["STATE"].strip(),r["ENROLLMENT STATE"].strip()))
        pacs[p[1]].add(p[0])
        n=key(r["NPI"],r"[0-9]{10}")
        if n:npis[n].add(p)
    need(all(sum(v.values())==counts["rows"] for v in kinds.values()),"enrollment field counts")
    return ids,{"counts":dict(counts),"field_states":{k:dict(v) for k,v in kinds.items()},
        "distinct_valid_enrollment_pac_pairs":len(ids),"pairs_with_multiple_rows":sum(len(v)>1 for v in ids.values()),
        "distinct_valid_provider_pacs":len(pacs),"provider_pacs_with_multiple_enrollments":sum(len(v)>1 for v in pacs.values()),
        "distinct_valid_npis":len(npis),"npis_with_multiple_enrollment_pac_pairs":sum(len(v)>1 for v in npis.values())}
def owner_audit(stream,family,ids):
    counts=Counter();role_counts=Counter();classes=Counter();labels=Counter();pct=defaultdict(Counter);dates=Counter()
    flags={f:Counter() for f in FLAGS_BY[family]}
    flag_entities={f:defaultdict(set) for f in FLAGS_BY[family]}
    roles_by_owner=defaultdict(set);matched_by_owner=defaultdict(set);classes_by_owner=defaultdict(set)
    pairs=set();triples=set();observed_types=Counter();pct_threshold=Counter();label_conflicts=Counter()
    for r in stream:
        typ=r["TYPE - OWNER"].strip()
        observed_types[typ if typ in ("I","O") else "unrecognized"]+=1
        if typ=="I":continue
        need(typ=="O","unexpected owner type")
        counts["organizational_rows"]+=1
        code,cls,lab=role(r,family)
        role_counts[code]+=1;classes[cls]+=1;labels[lab]+=1
        if lab!="matches":label_conflicts[code]+=1
        state,n=percentage(r["PERCENTAGE OWNERSHIP"]);pct[code][state]+=1
        if code in ("01","34","35","36","37") and lab=="matches":
            pct_threshold["missing_or_invalid" if n is None else "below_label_threshold" if n<5 else "at_least_5"]+=1
        dates[date_state(r["ASSOCIATION DATE - OWNER"])[0]]+=1
        owner=key(r["ASSOCIATE ID - OWNER"],r"[0-9]{10}");enroll=pair(r)
        counts["valid_owner_pac" if owner else "invalid_or_missing_owner_pac"]+=1
        counts["exact_enrollment_pac_candidate" if enroll in ids else "no_exact_enrollment_pac_candidate"]+=1
        for f,c in flags.items():
            v=flag(r[f+" - OWNER"]);c[v]+=1
            if owner:flag_entities[f][owner].add(v)
        if owner:
            roles_by_owner[owner].add(code);classes_by_owner[owner].add(cls)
            if enroll:
                pairs.add((owner,*enroll));triples.add((owner,*enroll,code))
                if enroll in ids:matched_by_owner[owner].add(enroll)
    n=counts["organizational_rows"]
    need(sum(role_counts.values())==sum(classes.values())==sum(labels.values())==sum(dates.values())==n,"owner role counts")
    need(all(sum(v.values())==n for v in flags.values()),"organization flag counts")
    need(sum(sum(v.values()) for v in pct.values())==n,"percentage states")
    flag_summaries={}
    for f,c in flags.items():
        entities=flag_entities[f]
        flag_summaries[f]={"rows":dict(c),"valid_pacs_with_yes":sum("yes" in s for s in entities.values()),
             "valid_pacs_with_no":sum("no" in s for s in entities.values()),
             "valid_pacs_with_both_yes_no":sum({"yes","no"}<=s for s in entities.values()),
             "valid_pacs_yes_without_no_or_unrecognized":sum("yes" in s and not ({"no","unrecognized"}&s) for s in entities.values())}
    bins=Counter(memberships(len(v)) for v in matched_by_owner.values())
    need(sum(bins.values())==len(matched_by_owner),"portfolio size counts")
    return set(roles_by_owner),{"input_owner_type_counts":dict(observed_types),"counts":dict(counts),
       "role_code_counts":dict(role_counts),"role_class_counts":dict(classes),"role_text_agreement":dict(labels),
       "role_text_conflicts_by_code":dict(label_conflicts),"ownership_percentage_states_by_role":{k:dict(v) for k,v in pct.items()},
       "threshold_code_percentage_states":dict(pct_threshold),"association_date_states":dict(dates),"flags":flag_summaries,
       "distinct_valid_organization_pac_tokens":len(roles_by_owner),
       "organization_pacs_with_multiple_role_codes":sum(len(v)>1 for v in roles_by_owner.values()),
       "distinct_valid_org_enrollment_provider_pairs":len(pairs),"distinct_valid_org_enrollment_provider_role_keys":len(triples),
       "organization_pacs_with_exact_enrollment_candidate":len(matched_by_owner),
       "candidate_enrollment_count_bands":dict(bins),
       "organization_pacs_with_multiple_matched_enrollments":sum(len(v)>1 for v in matched_by_owner.values())}
def chow_audit(stream,ids):
    counts=Counter();codes=Counter();labels=Counter();dates=Counter();years=Counter();links={s:Counter() for s in ("BUYER","SELLER")}
    identity=Counter();candidate_keys=set()
    for r in stream:
        counts["rows"]+=1;c=r["CHOW TYPE CODE"].strip();known=c in CHOW
        codes[c if known else "blank" if not c else "unrecognized"]+=1
        t=normalized(r["CHOW TYPE TEXT"]);labels["matches" if known and t==CHOW[c] else "unrecognized_code" if not known else "blank_text" if not t else "text_differs"]+=1
        state,d=date_state(r["EFFECTIVE DATE"]);dates[state]+=1
        if d:years[str(d.year)]+=1;counts["before_2016"]+=int(d<date(2016,1,1))
        b,s=pair(r," - BUYER"),pair(r," - SELLER")
        if b and s and known and d:candidate_keys.add((*b,*s,c,d.isoformat()))
        for side,p in (("BUYER",b),("SELLER",s)):
            links[side]["exact_enrollment_pac_candidate" if p in ids else "no_exact_enrollment_pac_candidate"]+=1
            if p in ids:
                cn=r["CCN - "+side].strip()
                links[side]["candidate_ccn_text_agrees" if cn and any(x[0]==cn for x in ids[p]) else "candidate_ccn_missing_or_differs"]+=1
        for f in ("CCN","ASSOCIATE ID","ENROLLMENT ID"):
            x,y=r[f+" - BUYER"].strip(),r[f+" - SELLER"].strip()
            identity[f+"/"+("same_text" if x and y and x==y else "different_text" if x and y else "one_or_both_missing")]+=1
    n=counts["rows"];need(sum(codes.values())==sum(labels.values())==sum(dates.values())==n,"CHOW counts")
    return {"counts":dict(counts),"code_counts":dict(codes),"code_text_agreement":dict(labels),"effective_date_states":dict(dates),
            "parsed_effective_year_counts":dict(years),"buyer_seller_identity_text_counts":dict(identity),
            "enrollment_link_candidates":{k:dict(v) for k,v in links.items()},
            "distinct_valid_candidate_transaction_keys":len(candidate_keys)}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path)
    a=p.parse_args();need(not a.output.exists(),"new output required")
    pins={s["key"]:s for s in read(LOCK)["sources"]};headers={s["source"]:[f["field"] for f in s["fields"]] for s in read(HEADERS)["sources"]}
    out={};orgs={};source_pins={}
    for family in ("hospital","snf"):
        keys=[family+"-"+k for k in ("enrollment","owner","chow")]
        with tempfile.TemporaryDirectory(prefix="pecos-role-audit-") as d:
            paths={k:materialize(pins[k],a.raw_dir,Path(d),a.download) for k in keys}
            streams={k:rows(paths[k],pins[k],headers[k]) for k in keys}
            ids,en=enrollment_audit(streams[keys[0]])
            orgs[family],own=owner_audit(streams[keys[1]],family,ids)
            ch=chow_audit(streams[keys[2]],ids)
        need(en["counts"]["rows"]==pins[keys[0]]["stored_rows"] and ch["counts"]["rows"]==pins[keys[2]]["stored_rows"],"retained counts")
        need(own["counts"]["organizational_rows"]==pins[keys[1]]["stored_rows"] and own["input_owner_type_counts"].get("I",0)==pins[keys[1]]["excluded_rows"],"owner scope")
        out[family]={"enrollment":en,"owner":own,"chow":ch}
        source_pins.update({k:{f:pins[k][f] for f in ("sha256","release","input_rows","stored_rows","excluded_rows")} for k in keys})
    result={"format_version":1,"as_of":AS_OF.isoformat(),"sources":source_pins,"publisher_dictionaries":DOCS,
       "role_domain":ROLES,"role_classification":CLASSES,"change_of_ownership_domain":CHOW,"families":out,
       "shared_literal_valid_organization_pac_tokens":len(orgs["hospital"]&orgs["snf"]),
       "distinct_literal_valid_organization_pac_tokens_across_families":len(orgs["hospital"]|orgs["snf"]),
       "limitations":["Only organizational owner rows; individual rows skipped before other fields. Flags self-reported and may vary by enrollment. Blank differs from no.",
        "Role code and text must agree for interpretation. Unknown values remain aggregate unresolved counts. No raw IDs, names, addresses, private data, or row-level publication.",
        "Candidate enrollment links use exact family and strict 15-character enrollment/10-digit PAC. Not unique physical sites, verified legal ownership or current control.",
        "No ownership percentage totals: individuals excluded, direct/indirect/financial roles and overlapping enrollments differ. Below-threshold values are review flags, not legal conclusions.",
        "Slash dates with two plausible interpretations are not coerced. CHOW records are reported changes, not unique deeds or verified current owners."]}
    with a.output.open("x",encoding="utf-8") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print("PECOS_ROLE_SEMANTIC_AUDIT",json.dumps(result,separators=(",",":"),sort_keys=True),flush=True)
if __name__=="__main__":main()
