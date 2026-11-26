"""Targeted, reproducible Care Compare enrichment; only approved institutional capacity and aggregate evidence.

Preserve old SQLite source snapshot and raw release pins. Apply a separate
versioned public projection correction only to the existing LTCH capacity field.
No new individual owner, service, survey, or certification registry rows.
"""
import argparse,csv,hashlib,json,re,tempfile
from collections import Counter
from pathlib import Path
from restore_snapshot import materialize,verify_raw
import facilitysignal as fs

ROOT=Path(__file__).resolve().parent
DIRECTORY=ROOT/"web/public-directory"
EVIDENCE=ROOT/"research/qualified_data_use_20261126.json"
LOCK=ROOT/"research/snapshot_release_20261125.json"
HEADERS=ROOT/"research/care_compare_pecos_exact_headers_20261126.json"
LTCH="long-term-hospital"
HHA="home-health"
DICT_LTCH="https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/long_term_care_hospital/LTCH_Data_Dictionary.pdf"
DICT_HHA="https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/home_health/HHS_Data_Dictionary.pdf"
REUSE_LTCH="https://data.cms.gov/provider-data/topics/long-term-care-hospitals/about-using-government-data"
REUSE_HHA="https://data.cms.gov/provider-data/topics/home-health-services/about-using-government-data"
OWNERSHIP={"non-profit":"Non-Profit","proprietary":"Proprietary","government operated":"Government Operated"}
SERVICES=("Nursing Care","Physical Therapy","Occupational Therapy","Speech Pathology","Medical Social","Home Health Aide")
MARKERS={"":"blank","-":"dash_marker","not available":"not_available","not applicable":"not_applicable","n/a":"n_a","unknown":"literal_unknown"}

def need(ok,msg):
    if not ok:raise ValueError(msg)
def read(path):return json.loads(path.read_text(encoding="utf-8"))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def json_bytes(obj,compact=False):
    return (json.dumps(obj,ensure_ascii=False,separators=(",",":") if compact else None,
                       indent=None if compact else 2,sort_keys=not compact)+"\n").encode()
def quantity(raw):
    v=raw.strip()
    if re.fullmatch(r"[0-9]{1,12}",v):return str(int(v)),"reported_integer"
    return "",MARKERS.get(v.casefold(),"unrecognized")
def classify(raw,domain):
    v=raw.strip().casefold()
    return domain.get(v,MARKERS.get(v,"unrecognized"))

def source_rows(path,pin,header):
    verify_raw(path,pin)
    with path.open(encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        need(reader.fieldnames==header,"exact raw header mismatch")
        result={}
        for row in reader:
            need(None not in row and all(v is not None for v in row.values()),"malformed row")
            normalized={fs.clean_key(k):v.strip() for k,v in row.items()}
            v=fs.normalize_facility(pin["key"],normalized)
            key=(v[1],v[5])
            need(key not in result,"duplicate source identity")
            result[key]=(row,dict(zip(("ccn","name","address","city","state","zip"),v[1:7])))
    need(len(result)==pin["stored_rows"]==pin["input_rows"],"row reconciliation")
    verify_raw(path,pin)
    return result

def compare_directory(shard,pin,rows):
    need(shard["source"]==pin["key"] and shard["release"]==pin["release"] and
         shard["row_count"]==len(shard["records"])==len(rows),"source/shard metadata mismatch")
    seen=set()
    for r in shard["records"]:
        k=(r["ccn"],r["state"])
        need(k not in seen and k in rows,"directory/source identifier mismatch")
        need(set(r)=={"ccn","name","address","city","state","zip","capacity"},"unexpected public columns")
        need({f:r[f] for f in rows[k][1]}==rows[k][1],"directory/source identity fields differ")
        seen.add(k)
    need(seen==set(rows),"unmatched source identity")

def build(ltch,hha,root=ROOT):
    pins={s["key"]:s for s in read(root/"research/snapshot_release_20261125.json")["sources"]}
    headers={s["source"]:[x["field"] for x in s["fields"]] for s in read(root/"research/care_compare_pecos_exact_headers_20261126.json")["sources"]}
    lr=source_rows(ltch,pins[LTCH],headers[LTCH])
    hr=source_rows(hha,pins[HHA],headers[HHA])
    directory=root/"web/public-directory"
    shard=read(directory/(LTCH+".json"))
    compare_directory(shard,pins[LTCH],lr)
    compare_directory(read(directory/(HHA+".json")),pins[HHA],hr)
    manifest=read(directory/"manifest.json")
    prior=manifest.get("field_enrichments",{}).get(LTCH)
    old_bytes=(directory/(LTCH+".json")).read_bytes()
    old_sha=hashlib.sha256(old_bytes).hexdigest()
    counts=Counter()
    values=[]
    for r in shard["records"]:
        row,_=lr[(r["ccn"],r["state"])]
        capacity,status=quantity(row["Total Number of Beds"])
        need(r["capacity"]=="" or (prior and r["capacity"]==capacity),"unexpected preexisting capacity")
        r["capacity"]=capacity
        counts[status]+=1
        if status=="reported_integer":values.append(int(capacity))
    need(len(values)==305 and sum(values)==21765 and len(lr)==311,"LTCH audited aggregate mismatch")
    projected=json_bytes(shard,compact=True)
    projected_sha=hashlib.sha256(projected).hexdigest()
    if prior:need(old_sha==projected_sha==prior["projection_sha256"],"prior enrichment changed")
    evidence={"format_version":1,"as_of":"2026-11-26","scope":"Selected institutional capacity and national aggregates from exact pinned releases; not current operation, equipment, legal ownership or confirmed procurement.",
      "ltch":{"source_sha256":pins[LTCH]["sha256"],"release":pins[LTCH]["release"],"source":pins[LTCH]["landing_url"],
          "dictionary":DICT_LTCH,"reuse":REUSE_LTCH,"source_field":"Total Number of Beds",
          "rows":len(lr),"reported":len(values),"unknown":len(lr)-len(values),"sum":sum(values),"min":min(values),"max":max(values),"zero":values.count(0),
          "value_states":dict(sorted(counts.items()))},
      "hha":{"source_sha256":pins[HHA]["sha256"],"release":pins[HHA]["release"],"source":pins[HHA]["landing_url"],
          "dictionary":DICT_HHA,"reuse":REUSE_HHA,"rows":len(hr),"ownership":{},"services":{}}}
    owner=Counter(classify(row["Type of Ownership"],OWNERSHIP) for row,_ in hr.values())
    labels=list(OWNERSHIP.values())
    evidence["hha"]["ownership"]={label:owner[label] for label in labels}
    evidence["hha"]["ownership"]["other_or_missing"]=len(hr)-sum(owner[k] for k in labels)
    evidence["hha"]["ownership_other_states"]={k:v for k,v in sorted(owner.items()) if k not in labels}
    for name in SERVICES:
        field="Offers "+name+" Services"
        vals=Counter(classify(row[field],{"yes":"yes","no":"no"}) for row,_ in hr.values())
        need(sum(vals.values())==len(hr),"HHA service reconciliation")
        evidence["hha"]["services"][name]={"yes":vals["yes"],"no":vals["no"],"other_or_missing":len(hr)-vals["yes"]-vals["no"],
            "other_states":{k:v for k,v in sorted(vals.items()) if k not in ("yes","no")}}
    profile=read(root/"research/iqies_raw_field_profile_20261126.json")
    dictionary=read(root/"research/iqies_full_dictionary_metadata_20261126.json")
    need(profile["source_sha256"]==pins["iqies"]["sha256"] and profile["qualification_run"]==45821921407,"iQIES evidence drift")
    fields={f["field"]:f for f in profile["fields"]}
    definitions={f["field"]:f for f in dictionary["fields"]}
    evidence["asc"]={"source_sha256":profile["source_sha256"],"period":profile["period"],
        "rows":profile["provider_scope_counts"]["ASC"],"services":{}}
    for label,field,mapping in (("Pharmacy","phrmcy_srvc_cd","M5"),("Laboratory","lab_srvc_cd","M5"),("Radiology","rdlgy_srvc_cd","M7")):
        d=definitions[field]["candidates"]
        need(len(d)==1 and d[0]["mapping_raw"]==mapping and "ASC" in d[0]["applicability"],"dictionary scope or mapping drift")
        rows=dictionary["mapping_sheets"][mapping]["entries"]
        scoped={r["code"]:r["label"].lower() for r in rows if r["provider_types"] is None or "ASC" in r["provider_types"].upper().split(", ")}
        need(set(scoped)=={"1","2","3","4"} and "direct" in scoped["1"] and "outside" in scoped["2"] and "combination" in scoped["3"] and "not provided" in scoped["4"],"publisher domain drift")
        f=fields[field];c=f["documented_code_counts"]["ASC"];s=f["scope_counts"]["ASC"]
        need(set(c)==set(scoped) and sum(c.values())==8040 and s["not_available"]==452 and s["rows"]==8492,"ASC actual code reconciliation")
        evidence["asc"]["services"][label]={"direct":c["1"],"outside":c["2"],"combination":c["3"],"not_provided":c["4"],"unavailable":s["not_available"]}
    index=read(root/"research/national_data_understanding_index_20261126.json")
    evidence["audit"]={k:index["totals"][k] for k in ("datasets","profiled_rows","columns","cells_checked","aggregate_value_profiles","presence_only_profiles","all_blank_fields")}
    metadata={"source_sha256":pins[LTCH]["sha256"],"release":pins[LTCH]["release"],"source_field":"Total Number of Beds",
          "unit":"reported total beds","projection_sha256":projected_sha,
          "prior_projection_sha256":prior["prior_projection_sha256"] if prior else old_sha,
          "numeric_rows":len(values),"unknown_rows":len(lr)-len(values),"sum":sum(values),
          "dictionary":DICT_LTCH,"reuse":REUSE_LTCH,"method":"exact source CCN/state and six institutional identity fields; original public capacity column only"}
    manifest.setdefault("field_enrichments",{})[LTCH]=metadata
    return projected,json_bytes(manifest,compact=True),json_bytes(evidence)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--download",action="store_true")
    p.add_argument("--raw-dir",type=Path)
    p.add_argument("--write",action="store_true",help="Explicit candidate checkout update; never run on an approved production snapshot")
    a=p.parse_args()
    need(a.write,"explicit --write required")
    pins={s["key"]:s for s in read(LOCK)["sources"]}
    with tempfile.TemporaryDirectory(prefix="qualified-care-compare-use-") as d:
        ltch=materialize(pins[LTCH],a.raw_dir,Path(d),a.download)
        hha=materialize(pins[HHA],a.raw_dir,Path(d),a.download)
        outputs=build(ltch,hha)
    # Only after every source, mapping, row identity and aggregate check passes.
    for path,data in zip((DIRECTORY/(LTCH+".json"),DIRECTORY/"manifest.json",EVIDENCE),outputs):
        path.write_bytes(data)
    print("QUALIFIED_DATA_USE",outputs[-1].decode(),flush=True)

if __name__=="__main__":main()
