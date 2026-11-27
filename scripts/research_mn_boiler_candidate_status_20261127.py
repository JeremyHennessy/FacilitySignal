"""Offline aggregate status audit for exact Minnesota boiler candidate pins."""
import collections as C
import csv, hashlib, io, json, sys, zipfile
from pathlib import Path
from research_mn_boiler_location_candidates_20261127 import CMS, DLI, REQUIRED, key, literal

RAW_EXCLUDED={"SCRAPPED","OUT OF SERV","OUT OF SERVICE","REMOVED/NOT FOUND","CONDEMNED"}
def state(value):
    status=literal(value)
    return "literal_active" if status=="ACTIVE" else "explicit_retired_out_of_service_or_not_found" if status in RAW_EXCLUDED else "other_or_unknown"

def analyze(root):
    modes=("literal","street_suffix_only")
    cms={m:C.defaultdict(list) for m in modes}
    for src,h in CMS.items():
        raw=(root/f"{src}.json").read_bytes()
        if hashlib.sha256(raw).hexdigest()!=h: raise ValueError("CMS pin mismatch")
        for v in json.loads(raw)["records"]:
            if v["state"]!="MN": continue
            for mode in modes:
                k=key(v["address"],"",v["city"],v["zip"],mode!="literal")
                if k is not None: cms[mode][k].append(src)
    raw=(root/"source.zip").read_bytes()
    if len(raw)!=8082131 or hashlib.sha256(raw).hexdigest()!=DLI: raise ValueError("DLI pin mismatch")
    matches={m:C.defaultdict(lambda:(set(),C.Counter())) for m in modes}
    n=0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        members=z.infolist()
        if len(members)!=1: raise ValueError("Unexpected ZIP layout")
        info=members[0]
        if (info.filename,info.file_size,info.CRC)!=("BPV_SNAP_11_27_2026.csv",58397370,0x9885b6be) or info.flag_bits&1:
            raise ValueError("Unqualified member")
        with z.open(info) as f, io.TextIOWrapper(f,encoding="cp1252",errors="strict",newline="") as txt:
            reader=csv.DictReader(txt,strict=True)
            fields=reader.fieldnames or []
            if len(fields)!=31 or len(set(fields))!=31 or not REQUIRED<=set(fields): raise ValueError("Unqualified header")
            for v in reader:
                n+=1
                if n>200000 or None in v or None in v.values(): raise ValueError("Unqualified row")
                for mode in modes:
                    k=key(v["Location_Address1"],v["Location_Address2"],v["Location_City"],v["Location_Zip"],mode!="literal")
                    if k is None or k not in cms[mode]: continue
                    ids,counts=matches[mode][k]
                    ids.add(v["Location_Record_ID"].strip())
                    kind=literal(v["Asset_Type"])
                    if kind=="BOILER": counts[state(v["Milestone"])]+=1
    expected={"literal":(10,151),"street_suffix_only":(116,951)}
    if n!=171503: raise ValueError("Source row discrepancy")
    result={}
    for mode in modes:
        if (len(matches[mode]),sum(sum(c.values()) for _,c in matches[mode].values()))!=expected[mode]:
            raise ValueError("Aggregate candidate reconciliation error")
        groups=C.defaultdict(C.Counter)
        for k,(ids,c) in matches[mode].items():
            p=len(cms[mode][k])>1
            d=len(ids)!=1 or "" in ids
            group="multiple_provider_and_dli_location" if p and d else "multiple_provider" if p else "multiple_or_missing_dli_location" if d else "one_provider_one_dli_location"
            for label in ("all",group):
                a=groups[label]
                a["candidate_address_keys"]+=1
                a["address_keys_with_boiler_rows"]+=bool(c)
                a["address_keys_with_literal_active_boiler_rows"]+=bool(c["literal_active"])
                a["address_keys_with_only_explicit_exclusion_boiler_rows"]+=bool(c) and sum(c.values())==c["explicit_retired_out_of_service_or_not_found"]
                for s in ("literal_active","explicit_retired_out_of_service_or_not_found","other_or_unknown"):
                    a[s+"_boiler_rows"]+=c[s]
        for field,total in groups["all"].items():
            if sum(a[field] for g,a in groups.items() if g!="all")!=total: raise ValueError("Nonexclusive ambiguity groups")
        result[mode]=groups
    return {"status":"AGGREGATE_RESEARCH_ONLY","input_dli_sha256":DLI,"input_cms_sha256":CMS,"source_rows_screened":n,"groups_by_matching_mode":result,"literal_exclusion_statuses":sorted(RAW_EXCLUDED),"scope":"CMS provider/DLI address-key candidates, not confirmed co-location, ownership or current operating state. Literal Active is a snapshot token, not a current finding. Other statuses are not inferred. The explicit exclusion group includes records marked not found; this is not proof of physical absence. No row output."}

if __name__=="__main__":
    if state(" Out of   Serv ")!="explicit_retired_out_of_service_or_not_found" or state("active")!="literal_active" or state("Exempt")!="other_or_unknown" or state("fees due")!="other_or_unknown": raise AssertionError("Literal status test")
    print(json.dumps(analyze(Path(sys.argv[1])),sort_keys=True,indent=2))
