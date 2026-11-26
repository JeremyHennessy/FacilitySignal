"""Pinned PECOS date convention and classification audit; aggregate only."""
import argparse,json,re,tempfile
from collections import Counter
from datetime import datetime,date
from pathlib import Path
from restore_snapshot import materialize
from pecos_role_semantic_audit import rows,read,need,LOCK,HEADERS,normalized
AS_OF=date(2026,11,26)
TYPES={f"00-{k}":v for k,v in [
("00","RELIGIOUS NON-MEDICAL HEALTH CARE INSTITUTION (RNHCI)"),("01","COMMUNITY MENTAL HEALTH CENTER"),
("02","COMPREHENSIVE OUTPATIENT REHABILITATION FACILITY"),("03","END-STAGE RENAL DISEASE FACILITY (ESRD)"),
("04","FEDERALLY QUALIFIED HEALTH CENTER (FQHC)"),("05","HISTOCOMPATIBILITY LABORATORY"),
("06","HOME HEALTH AGENCY"),("08","HOSPICE"),("09","HOSPITAL"),("10","INDIAN HEALTH SERVICES FACILITY"),
("13","ORGAN PROCUREMENT ORGANIZATION (OPO)"),("14","OUTPATIENT PHYSICAL THERAPY/OCCUPATIONAL THERAPY/SPEECH PATHOLOGY SERVICES"),
("17","RURAL HEALTH CLINIC"),("18","SKILLED NURSING FACILITY"),("19","OTHER"),("24","RURAL EMERGENCY HOSPITAL"),
("34","OPIOID TREATMENT PROGRAM"),("85","CRITICAL ACCESS HOSPITAL")]}
def dates(s):
    s=s.strip()
    if not s:return "blank",{}
    formats={"mdy":"%m/%d/%Y","dmy":"%d/%m/%Y"} if re.fullmatch(r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}",s) else {"iso":"%Y-%m-%d"} if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",s) else {"compact_ymd":"%Y%m%d","compact_mdy":"%m%d%Y","compact_dmy":"%d%m%Y"} if re.fullmatch(r"[0-9]{8}",s) else {}
    parsed={}
    for key,fmt in formats.items():
        try:parsed[key]=datetime.strptime(s,fmt).date()
        except ValueError:pass
    if not parsed:return "invalid_or_other",{}
    if len(parsed)==1:return next(iter(parsed))+"_only",parsed
    return ("same_date_multiple_formats" if len(set(parsed.values()))==1 else "ambiguous_"+("slash" if "/" in s else "compact")),parsed
def classify(code,label):
    c=code.strip()
    if c not in TYPES:return "blank" if not c else "unknown_code"
    return c+"|"+("matches" if normalized(label)=="PART A PROVIDER - "+TYPES[c] else "blank_label" if not label.strip() else "label_differs")
def audit(key,stream):
    owner=key.endswith("-owner"); chow=key.endswith("-chow")
    fields=["ASSOCIATION DATE - OWNER"] if owner else ["EFFECTIVE DATE"] if chow else ["INCORPORATION DATE"]+(["REH CONVERSION DATE"] if key=="hospital-enrollment" else [])
    suffixes=[] if owner else [" - BUYER"," - SELLER"] if chow else [""]
    dc={f:Counter() for f in fields}; bounds={f:Counter() for f in fields}; types={s:Counter() for s in suffixes}; org=Counter(); n=excluded=0
    for r in stream:
        if owner:
            t=r["TYPE - OWNER"].strip()
            if t=="I":excluded+=1;continue
            need(t=="O","unknown owner type")
        n+=1
        for f in fields:
            state,p=dates(r[f]);dc[f][state]+=1
            for fmt,d in p.items():
                bounds[f][fmt+"|"+("future" if d>AS_OF else "before_2016" if d<date(2016,1,1) else "2016_through_asof")]+=1
        for s in suffixes:types[s][classify(r["PROVIDER TYPE CODE"+s],r["PROVIDER TYPE TEXT"+s])]+=1
        if not owner and not chow:
            v=normalized(r["ORGANIZATION TYPE STRUCTURE"])
            org[v if v in {"CORPORATION","LIMITED LIABILITY COMPANY","PARTNERSHIP","SOLE PROPRIETOR","OTHER",""} else "other_unreviewed"]+=1
    need(all(sum(c.values())==n for c in list(dc.values())+list(types.values())),"count mismatch")
    return {"retained":n,"excluded_individual":excluded,"date_format_states":dc,"candidate_date_bounds":bounds,"provider_code_label_states":types,"organization_structure_candidates":org}
def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path);a=p.parse_args()
    pins={s["key"]:s for s in read(LOCK)["sources"]}; headers={s["source"]:[f["field"] for f in s["fields"]] for s in read(HEADERS)["sources"]}
    out={}
    for key in ("hospital-enrollment","snf-enrollment","hospital-owner","snf-owner","hospital-chow","snf-chow"):
        pin=pins[key]
        with tempfile.TemporaryDirectory() as d:
            path=materialize(pin,a.raw_dir,Path(d),a.download)
            r=audit(key,rows(path,pin,headers[key]))
        need(r["retained"]==pin["stored_rows"] and r["excluded_individual"]==pin["excluded_rows"],"scope drift")
        out[key]={"sha256":pin["sha256"],"release":pin["release"],**r}
    with a.output.open("x") as f:json.dump(out,f,indent=2,sort_keys=True)
    print("PECOS_DATE_CLASSIFICATION",json.dumps(out,sort_keys=True))
if __name__=="__main__":main()
