"""Build/check the narrowly reviewed selected CMS PUF historical capacity projection.

No Azure access. Only the previously rehearsed, exact-hash public PUF fields.
Never write raw reports or alpha values, nor any monetary values. Do not publish
directly; the isolated branch workflow and release gate handle promotion.
"""
import argparse,hashlib,json,re
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from build_combined import require
from scripts import qualify_hcris_capacity_candidate as q
ROOT=Path(__file__).resolve().parents[1]
SCOPE="FY2024 selected CMS PUF historical report capacity; exact matched candidate cohort, not current certified capacity"
FORMS=("hospital","snf")
def expected(root):
    r=json.loads((root/"research/hcris_capacity_candidate_receipts_20261126.json").read_text())
    require(r["format_version"]==1 and set(r["forms"])==set(FORMS),"receipt schema")
    return r["forms"]
def encode(records,form):
    return (json.dumps({"version":1,"scope":SCOPE,"form":form,"records":records},sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
def validate(raw,form,receipt,root):
    require(len(raw)==receipt["ephemeral_candidate_bytes"] and hashlib.sha256(raw).hexdigest()==receipt["ephemeral_candidate_sha256"],"exact rehearsed projection bytes")
    pack=json.loads(raw)
    require(set(pack)=={"version","scope","form","records"} and pack["version"]==1 and pack["scope"]==SCOPE and pack["form"]==form,"projection envelope")
    records=pack["records"];require(isinstance(records,list) and len(records)==receipt["candidate_reports"],"report count")
    d=receipt["directory"];p=root/"web/public-directory"/(d["source"]+".json");b=p.read_bytes()
    require(hashlib.sha256(b).hexdigest()==d["sha256"],"directory bytes changed; requalification required")
    directory=json.loads(b);require(directory["source"]==d["source"] and directory["release"]==d["release"] and len(directory["records"])==d["rows"],"directory envelope")
    ids=defaultdict(Counter)
    for r in directory["records"]:ids[r["ccn"]][r["state"]]+=1
    fields=set(q.FIELDS[form].values());counts={k:Counter() for k in fields};periods=defaultdict(list);seen=set()
    for r in records:
        require(set(r)=={"report_key","ccn","state","period_begin","period_end","measures"} and set(r["measures"])==fields,"row allowlist")
        require(type(r["report_key"]) is str and re.fullmatch(r"[0-9]{1,20}",r["report_key"]) and r["report_key"] not in seen,"report key uniqueness")
        seen.add(r["report_key"])
        require(type(r["ccn"]) is str and re.fullmatch(r"[A-Z0-9]{6}",r["ccn"]) and type(r["state"]) is str and re.fullmatch(r"[A-Z]{2}",r["state"]),"source identity shape")
        require(ids[r["ccn"]][r["state"]]==1 and sum(ids[r["ccn"]].values())==1,"directory identity uniqueness")
        a,b=(date.fromisoformat(r[k]) for k in ("period_begin","period_end"))
        require(a.isoformat()==r["period_begin"] and b.isoformat()==r["period_end"] and date(2023,10,1)<=a<=date(2024,9,30) and a<=b,"FY2024 reporting period")
        periods[(r["ccn"],r["state"])].append((a,b))
        for k,v in r["measures"].items():
            require(v is None or type(v) is int and 0<=v<=9007199254740991,"numeric domain")
            counts[k]["missing" if v is None else "reported_zero" if v==0 else "reported_positive"]+=1
    require(len(periods)==receipt["candidate_providers"],"provider count")
    for rows in periods.values():
        for i,(a,b) in enumerate(rows):require(all(not(a<=d and c<=b) for c,d in rows[:i]),"period overlap")
    require({k:dict(v) for k,v in counts.items()}==receipt["field_value_states"],"value-state count mismatch")
    return {"form":form,"reports":len(records),"providers":len(periods),"sha256":receipt["ephemeral_candidate_sha256"],"field_value_states":receipt["field_value_states"]}
def build(root):
    pins=expected(root);payloads={}
    for form in FORMS:
        def sink(records,receipt):
            p=pins[form]
            require(all(receipt[k]==p[k] for k in receipt),"rehearsal receipt drift")
            raw=encode(records,form)
            validate(raw,form,p,root)
            payloads[form]=raw
        q.run(form,root,candidate_sink=sink)
    require(set(payloads)==set(FORMS),"both projections required")
    out=root/"web/hcris-capacity"
    require(not out.exists(),"refuse overwrite of existing projection")
    out.mkdir()
    for form in FORMS:
        with (out/(form+".json")).open("xb") as f:f.write(payloads[form])
def check(root):
    out=root/"web/hcris-capacity";pins=expected(root)
    require(out.is_dir() and {p.name for p in out.iterdir()}=={f+".json" for f in FORMS},"projection file allowlist")
    return [validate((out/(f+".json")).read_bytes(),f,pins[f],root) for f in FORMS]
def main():
    p=argparse.ArgumentParser();p.add_argument("--build",action="store_true");p.add_argument("--check",action="store_true");a=p.parse_args()
    require(a.build!=a.check,"choose exactly one mode")
    if a.build:build(ROOT)
    print("PUBLIC_HCRIS_CAPACITY_CHECK_PASS",json.dumps(check(ROOT),sort_keys=True),flush=True)
if __name__=="__main__":main()
