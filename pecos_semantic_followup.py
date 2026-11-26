"""Narrow follow-up: exact CHOW label variants and omitted hospital subgroup flags.

Uses three small pinned source files only, no repeated large owner downloads.
Does not coerce dates or create facility-level relationships.
"""
import argparse,json,tempfile
from collections import Counter
from pathlib import Path
from restore_snapshot import materialize
from pecos_role_semantic_audit import rows,read,need,LOCK,HEADERS,normalized,flag,date_state

# The 2026-07 dictionary appends (CHOW); the 2026-01 dictionary does not.
CHOW_LABELS={"AM":{"ACQUISITION/MERGER":"current_dictionary"},
             "CH":{"CHANGE OF OWNERSHIP (CHOW)":"current_dictionary","CHANGE OF OWNERSHIP":"documented_earlier_dictionary_variant"},
             "CO":{"CONSOLIDATION":"current_dictionary"}}
SUBGROUPS=("GENERAL","ACUTE CARE","ALCOHOL DRUG","CHILDRENS","LONG-TERM","PSYCHIATRIC","REHABILITATION","SHORT-TERM",
           "SWING-BED APPROVED","PSYCHIATRIC UNIT","REHABILITATION UNIT","SPECIALTY HOSPITAL","OTHER")
def chow(rows):
    counts=Counter();by_code={k:Counter() for k in CHOW_LABELS}
    for r in rows:
        c=r["CHOW TYPE CODE"].strip();s=normalized(r["CHOW TYPE TEXT"]);counts["rows"]+=1
        if c not in CHOW_LABELS:counts["unknown_code"]+=1;continue
        st=CHOW_LABELS[c].get(s,"blank_text" if not s else "unresolved_text")
        by_code[c][st]+=1;counts[st]+=1
    need(sum(v for k,v in counts.items() if k!="rows")==counts["rows"],"CHOW label count")
    return {"counts":dict(counts),"by_code":{k:dict(v) for k,v in by_code.items()}}
def subgroups(rows):
    fields={f:Counter() for f in SUBGROUPS};conversion=Counter();refs=Counter();dates=Counter();joint=Counter();n=0
    for r in rows:
        n+=1;yes=0
        for f,c in fields.items():
            v=flag(r["SUBGROUP - "+f]);c[v]+=1;yes+=int(v=="yes")
        joint[str(yes)]+=1
        v=flag(r["REH CONVERSION FLAG"]);conversion[v]+=1
        d,_=date_state(r["REH CONVERSION DATE"]);dates[d]+=1
        p="reference_present" if r["CAH OR HOSPITAL CCN"].strip() else "reference_blank"
        refs[v+"/"+p]+=1
    need(all(sum(v.values())==n for v in fields.values()) and sum(conversion.values())==sum(refs.values())==sum(dates.values())==n,"subgroup reconciliation")
    return {"rows":n,"subgroup_flag_counts":{f:dict(c) for f,c in fields.items()},
            "affirmative_subgroup_count_distribution":dict(joint),"reh_conversion_flag":dict(conversion),
            "reh_conversion_date_states":dict(dates),"reh_conversion_reference_presence":dict(refs)}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path)
    a=p.parse_args();need(not a.output.exists(),"new output required")
    pins={s["key"]:s for s in read(LOCK)["sources"]}
    headers={s["source"]:[f["field"] for f in s["fields"]] for s in read(HEADERS)["sources"]}
    result={}
    for k in ("hospital-enrollment","hospital-chow","snf-chow"):
        with tempfile.TemporaryDirectory(prefix="pecos-followup-") as d:
            path=materialize(pins[k],a.raw_dir,Path(d),a.download)
            stream=rows(path,pins[k],headers[k])
            result[k]=subgroups(stream) if k.endswith("-enrollment") else chow(stream)
    result={"format_version":1,"source_hashes":{k:pins[k]["sha256"] for k in result},"result":result,
            "dictionary_evidence":{"current_hospital":"https://data.cms.gov/sites/default/files/2026-07/Hospital_CHOW_Data_Dictionary.pdf",
            "current_snf":"https://data.cms.gov/sites/default/files/2026-07/SNF_CHOW_Data_Dictionary.pdf",
            "earlier_hospital":"https://data.cms.gov/sites/default/files/2026-01/Hospital_CHOW_Data_Dictionary.pdf",
            "subgroups":"https://data.cms.gov/sites/default/files/2026-07/Hospital_Enrollments_Data_Dictionary.pdf"},
            "limits":["Known wording variants only, source code preserved, no guessed aliases. No date coercion, current operations, property ownership or individual records.",
                      "Subgroups are self-reported enrollment flags; counts can overlap. REH predecessor reference presence does not establish a canonical site link."]}
    with a.output.open("x",encoding="utf-8") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print("PECOS_TARGETED_FOLLOWUP",json.dumps(result,separators=(",",":"),sort_keys=True),flush=True)
if __name__=="__main__":main()
