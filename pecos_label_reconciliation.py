"""Reconcile exact PECOS provider type wording and bounded structure candidates.

No individual owner files, free-text labels, identifiers or normalized dates emitted.
"""
import argparse,json,tempfile
from collections import Counter
from pathlib import Path
from restore_snapshot import materialize
from pecos_role_semantic_audit import rows,read,need,LOCK,HEADERS,normalized,ROOT
# Exact observed Part A code domain from July 2026 enrollment and CHOW dictionaries.
TYPES={
"00-04":"FEDERALLY QUALIFIED HEALTH CENTER (FQHC)","00-06":"HOME HEALTH AGENCY",
"00-09":"HOSPITAL","00-10":"INDIAN HEALTH SERVICES FACILITY",
"00-14":"OUTPATIENT PHYSICAL THERAPY/OCCUPATIONAL THERAPY/SPEECH PATHOLOGY SERVICES",
"00-17":"RURAL HEALTH CLINIC","00-18":"SKILLED NURSING FACILITY","00-19":"OTHER",
"00-24":"RURAL EMERGENCY HOSPITAL","00-85":"CRITICAL ACCESS HOSPITAL"}
PREFIX="PART A PROVIDER - "
# Separately documented CMS general Medicare enrollment dictionary wording.
REH_ALT=PREFIX+"RURAL EMERGENCY HOSPITAL (REH)"
FORM_STRUCTURE={"CORPORATION","LIMITED LIABILITY COMPANY","PARTNERSHIP","SOLE PROPRIETOR","OTHER",
"FEDERAL","STATE","CITY","COUNTY","CITY-COUNTY","HOSPITAL DISTRICT"}
# Candidate text variants only; not an authoritative export-code table.
VARIANTS={"LLC":"LIMITED LIABILITY COMPANY","LIMITED LIABILITY COMPANY (LLC)":"LIMITED LIABILITY COMPANY",
"GOVERNMENT":"government_unspecified","GOVERNMENTAL":"government_unspecified",
"GENERAL PARTNERSHIP":"PARTNERSHIP","LIMITED PARTNERSHIP":"PARTNERSHIP"}
def classify(code,label):
    c=code.strip();t=normalized(label)
    if c not in TYPES:return "unknown_code" if c else "blank_code"
    if t==PREFIX+TYPES[c]:return c+"|matches"
    if c=="00-24" and t==REH_ALT:return c+"|documented_general_dictionary_variant"
    return c+"|label_differs"
def structure(raw):
    v=normalized(raw)
    if not v:return "blank"
    if v in FORM_STRUCTURE:return v
    if v in VARIANTS:return "candidate_variant:"+VARIANTS[v]
    return "other_unreviewed"
def audit(key,stream,prior):
    chow=key.endswith("-chow")
    suffixes=(" - BUYER"," - SELLER") if chow else ("",)
    counts={s:Counter() for s in suffixes}
    structures=Counter();profit=Counter();cross=Counter();n=0
    for r in stream:
        n+=1
        for s in suffixes:counts[s][classify(r["PROVIDER TYPE CODE"+s],r["PROVIDER TYPE TEXT"+s])]+=1
        if not chow:
            st=structure(r["ORGANIZATION TYPE STRUCTURE"])
            p={"P":"proprietary","N":"nonprofit","":"blank"}.get(r["PROPRIETARY NONPROFIT"].strip(),"unreviewed")
            structures[st]+=1;profit[p]+=1;cross[st+"|"+p]+=1
    need(n==prior["retained"] and all(sum(v.values())==n for v in counts.values()),"row reconciliation")
    for s,c in counts.items():
        old=Counter()
        for k,v in c.items():old[k.replace("|documented_general_dictionary_variant","|label_differs")]+=v
        need(dict(old)==prior["provider_code_label_states"][s],"prior wording counts changed")
    if not chow:need(sum(structures.values())==sum(profit.values())==sum(cross.values())==n,"structure reconciliation")
    return {"rows":n,"provider_code_label_states":counts,"organization_structure_candidates":structures,"proprietary_nonprofit":profit,"structure_by_proprietary_nonprofit":cross}
def main():
    p=argparse.ArgumentParser();p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    pins={s["key"]:s for s in read(LOCK)["sources"]};headers={s["source"]:s for s in read(HEADERS)["sources"]}
    prior=read(ROOT/"research/pecos_date_classification_qualification_20261126.json");need(prior["qualification_run"]==45838449075,"prior run drift")
    out={}
    for k in ("hospital-enrollment","snf-enrollment","hospital-chow","snf-chow"):
        pin=pins[k];h=headers[k];pr=prior["sources"][k]
        need(pr["sha256"]==h["source_sha256"]==pin["sha256"],"source provenance")
        with tempfile.TemporaryDirectory() as d:
            path=materialize(pin,a.raw_dir,Path(d),a.download)
            result=audit(k,rows(path,pin,[f["field"] for f in h["fields"]]),pr)
        need(result["rows"]==pin["stored_rows"],"pinned row count")
        out[k]={"sha256":pin["sha256"],"release":pin["release"],**result}
    result={"sources":out,"dictionaries":["https://data.cms.gov/sites/default/files/2026-07/Hospital_Enrollments_Data_Dictionary.pdf","https://data.cms.gov/sites/default/files/2026-07/SNF_Enrollments_Data_Dictionary.pdf","https://data.cms.gov/sites/default/files/2026-07/Hospital_CHOW_Data_Dictionary.pdf","https://data.cms.gov/resources/medicare-fee-for-service-public-provider-enrollment-data-dictionary","https://www.cms.gov/Medicare/CMS-Forms/CMS-Forms/Downloads/cms855a.pdf"],"limits":"Exact code/label corroboration only. Structure form options and bounded candidate variants are not export-domain confirmation. No source values outside the explicit domain, no ownership inference or date normalization."}
    with a.output.open("x") as f:json.dump(result,f,indent=2,sort_keys=True)
    print("PECOS_LABEL_RECONCILIATION",json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
