"""Qualify omitted nursing citation fields and publisher chain/affiliation evidence.

All source data are ephemeral. Output only national aggregate counts. Never
resolve ownership, present-day compliance, dispute outcome or physical sites.
"""
import argparse,csv,json,re,tempfile
from collections import Counter,defaultdict
from datetime import datetime,date
from pathlib import Path
from restore_snapshot import materialize,verify_raw
from collect_registry import source_encoding,open_csv
from pos_raw_field_profile import read,need,LOCK

ROOT=Path(__file__).resolve().parent
HEADERS=ROOT/"research/care_compare_pecos_exact_headers_20261126.json"
DOCS={"nursing_dictionary":"https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/nursing_home/NH_Data_Dictionary.pdf",
      "pecos_dictionary":"https://data.cms.gov/sites/default/files/2026-07/SNF_Enrollments_Data_Dictionary.pdf",
      "pecos_guidance":"https://data.cms.gov/sites/default/files/2026-07/SNF_Data_Guidance.pdf"}
FLAGS=("Standard Deficiency","Complaint Deficiency","Infection Control Inspection Deficiency","Citation under IDR","Citation under IIDR")
def yn(value):
    s=value.strip()
    return "yes" if s=="Y" else "no" if s=="N" else "blank" if not s else "unrecognized"
def code(value,domain):
    s=value.strip()
    return s if s in domain else "blank" if not s else "unrecognized"
def day(value):
    s=value.strip()
    for fmt in ("%Y-%m-%d","%m/%d/%Y"):
        try:return datetime.strptime(s,fmt).date()
        except ValueError:pass
    return None
def version(value):
    s=value.strip().casefold()
    return s if s in ("old","new") else "blank" if not s else "unrecognized"
def id_token(value):
    s=value.strip()
    return s if re.fullmatch(r"[0-9]{1,8}",s) else None
def ccn(value):
    s=value.strip()
    return s if re.fullmatch(r"[A-Z0-9]{6}",s) else None
def clean_name(s):return " ".join(s.upper().split())
def records(path,pin,header):
    verify_raw(path,pin)
    enc="utf-8-sig" if pin["family"]=="care-compare" else source_encoding(path,pin["metadata"]["zipped"])
    n=0
    with open_csv(path,pin.get("metadata",{}).get("zipped",False),enc) as f:
        reader=csv.DictReader(f)
        need(reader.fieldnames==header,"exact pinned source header mismatch")
        for row in reader:
            need(None not in row and all(v is not None for v in row.values()),"malformed raw row")
            n+=1
            yield row
    need(n==pin["input_rows"]==pin["stored_rows"],"source row count mismatch")
    verify_raw(path,pin)
def citation(rows,fire):
    flags={f:Counter() for f in FLAGS}
    joint=Counter();types=Counter();cycles=Counter();versions=Counter();version_date=Counter()
    n=0
    for row in rows:
        n+=1
        states={f:yn(row[f]) for f in FLAGS}
        for f,v in states.items():flags[f][v]+=1
        joint[states["Citation under IDR"]+"/"+states["Citation under IIDR"]]+=1
        types["/".join(states[f] for f in FLAGS[:3])]+=1
        cycles[code(row["Inspection Cycle"],{"1","2","3"})]+=1
        if fire:
            v=version(row["Tag Version"]);versions[v]+=1
            d=day(row["Survey Date"])
            if not d or v not in ("old","new"):version_date["not_comparable"]+=1
            else:version_date["agrees" if (v=="new")== (d>=date(2016,7,5)) else "disagrees"]+=1
    need(all(sum(c.values())==n for c in flags.values()),"flag reconciliation")
    need(sum(joint.values())==sum(types.values())==sum(cycles.values())==n,"joint reconciliation")
    if fire:need(sum(versions.values())==sum(version_date.values())==n,"tag version reconciliation")
    return {"rows":n,"flags":{f:dict(c) for f,c in flags.items()},
            "idr_iidr_joint_counts":dict(joint),"inspection_flag_joint_counts":dict(types),
            "inspection_cycle_codes":dict(cycles),
            "tag_version":dict(versions) if fire else None,
            "tag_version_date_agreement":dict(version_date) if fire else None}
def state_pair(a,b):
    return "same" if a and b and a==b else "different" if a and b else "missing"
def chain_audit(nursing,enrollment):
    ns={};groups=defaultdict(list);name_ids=defaultdict(set)
    field=Counter()
    for r in nursing:
        key=ccn(r["CMS Certification Number (CCN)"])
        need(key and key not in ns,"duplicate or invalid Care Compare CCN")
        raw=r["Chain ID"].strip();token=id_token(raw)
        name=clean_name(r["Chain Name"])
        size=r["Number of Facilities in Chain"].strip()
        field["rows"]+=1
        field["valid_chain_id"]+=int(token is not None)
        field["blank_chain_id"]+=int(not raw)
        field["unrecognized_chain_id"]+=int(bool(raw) and token is None)
        field["chain_id_name_both_populated"]+=int(bool(token and name))
        field["chain_id_name_conflict"]+=int(bool(token)!=bool(name))
        field["chain_id_size_conflict"]+=int(bool(token)!=bool(size))
        ns[key]=(r["State"].strip(),token,name)
        if token:
            groups[token].append((name,size))
            if name:name_ids[name].add(token)
    need(field["rows"]==sum(field[k] for k in ("valid_chain_id","blank_chain_id","unrecognized_chain_id")),"chain id counts")
    gs=Counter();bands=Counter()
    for token,items in groups.items():
        size=len(items);names={n for n,s in items if n};rawsizes={s for n,s in items}
        gs["groups"]+=1;gs["single_reported_name"]+=int(len(names)==1)
        gs["multiple_reported_names"]+=int(len(names)>1)
        gs["missing_name_groups"]+=int(not names)
        gs["consistent_reported_size"]+=int(len(rawsizes)==1 and "" not in rawsizes)
        gs["reported_size_matches_observed_members"]+=int(rawsizes=={str(size)})
        gs["reported_size_mismatch_or_missing"]+=int(rawsizes!={str(size)})
        bands["1" if size==1 else "2-4" if size<=4 else "5-19" if size<=19 else "20-99" if size<=99 else "100+"]+=1
    pe=Counter();aff_ids=set();matched_n=set();paired=Counter();pair_name=Counter();counts=Counter()
    for r in enrollment:
        pe["rows"]+=1
        raw=r["AFFILIATION ENTITY ID"].strip()
        token=id_token(raw);name=clean_name(r["AFFILIATION ENTITY NAME"])
        pe["valid_affiliation_id"]+=int(token is not None)
        pe["blank_affiliation_id"]+=int(not raw)
        pe["unrecognized_affiliation_id"]+=int(bool(raw) and token is None)
        if token:aff_ids.add(token)
        key=ccn(r["CCN"])
        if key not in ns:pe["no_exact_nursing_ccn_candidate"]+=1;continue
        pe["exact_nursing_ccn_candidate"]+=1;matched_n.add(key);counts[key]+=1
        state,chain,chainname=ns[key]
        st=state_pair(state,r["STATE"].strip())
        pe["state_"+st]+=1
        if st!="same":continue
        paired["same_ccn_state_pairs"]+=1
        cls="both_populated_equal" if token and chain and token==chain else "both_populated_different" if token and chain else "both_missing_or_invalid" if not token and not chain else "one_missing_or_invalid"
        paired[cls]+=1
        if cls.startswith("both_populated"):
            pair_name[cls+"/"+("name_exact_text_equal" if name and chainname and name==chainname else "name_text_different" if name and chainname else "name_missing")]+=1
    need(pe["rows"]==pe["exact_nursing_ccn_candidate"]+pe["no_exact_nursing_ccn_candidate"],"enrollment match counts")
    need(pe["rows"]==sum(pe[k] for k in ("valid_affiliation_id","blank_affiliation_id","unrecognized_affiliation_id")),"affiliation counts")
    need(pe["exact_nursing_ccn_candidate"]==sum(pe["state_"+k] for k in ("same","different","missing")),"state reconciliation")
    need(paired["same_ccn_state_pairs"]==sum(paired[k] for k in ("both_populated_equal","both_populated_different","both_missing_or_invalid","one_missing_or_invalid")),"paired classification")
    return {"nursing":dict(field),"chains":{**dict(gs),"names_associated_with_multiple_chain_ids":sum(len(x)>1 for x in name_ids.values()),"observed_membership_size_bands":dict(bands)},
            "snf_enrollment":{**dict(pe),"distinct_affiliation_tokens":len(aff_ids),"distinct_nursing_ccns_with_candidate":len(matched_n),"nursing_ccns_with_multiple_enrollment_candidates":sum(x>1 for x in counts.values())},
            "cross_source_exact_ccn_state":dict(paired),"name_corroboration":dict(pair_name),
            "shared_literal_group_tokens":len(set(groups)&aff_ids),
            "limits":["Chain IDs and affiliation IDs are kept in their own publisher/release namespaces. Equal tokens and names are corroboration only, not proof of identical groups across releases.",
            "CMS methodology groups facilities by reported ownership, officer or management relationships; not legal property title or ultimate owner.",
            "No group names, identifiers, addresses or individual relationships retained. Missing affiliation cannot establish independence."]}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--group",choices=("citations","chains"),required=True);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path)
    a=p.parse_args();need(not a.output.exists(),"new output required")
    pins={s["key"]:s for s in read(LOCK)["sources"]}
    headers={s["source"]:[f["field"] for f in s["fields"]] for s in read(HEADERS)["sources"]}
    keys=("nursing-health","nursing-fire") if a.group=="citations" else ("nursing","snf-enrollment")
    with tempfile.TemporaryDirectory(prefix="nursing-field-audit-") as d:
        pths={k:materialize(pins[k],a.raw_dir,Path(d),a.download) for k in keys}
        streams={k:records(pths[k],pins[k],headers[k]) for k in keys}
        result={k:citation(streams[k],k=="nursing-fire") for k in keys} if a.group=="citations" else chain_audit(streams[keys[0]],streams[keys[1]])
    evidence={"format_version":1,"group":a.group,"source_pins":{k:{"sha256":pins[k]["sha256"],"release":pins[k]["release"],"rows":pins[k]["stored_rows"]} for k in keys},"documentation":DOCS,
       "documentation_limit":"Nursing dictionary extracted text says October 2026, visual footer says June 2026. Reviewed stable field descriptions in tables 2,6,7; release provenance unresolved. SNF July 2026 guidance v1.8.",
       "result":result,"limits":["Historical source evidence only. A dispute flag is not a dispute outcome or proof of present-day violation; multiple inspection flags can coexist. No individual-level output."]}
    with a.output.open("x",encoding="utf-8") as f:json.dump(evidence,f,indent=2,sort_keys=True);f.write("\n")
    print("NURSING_SEMANTIC_AUDIT",json.dumps(evidence,separators=(",",":"),sort_keys=True),flush=True)
if __name__=="__main__":main()
