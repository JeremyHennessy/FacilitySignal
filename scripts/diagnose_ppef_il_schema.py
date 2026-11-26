import json,re
import collect_registry as registry
from scripts.archive_ppef_enrollment import TITLE
from scripts.archive_environment_state import il_records
from collections import Counter
c=registry.get_json("https://data.cms.gov/data.json")
series=[s for s in c["datasetSeries"] if s["title"]==TITLE]
v=series[0]["last"]["@id"]
d=[x for x in c["dataset"] if x["@id"]==v][0]
print("PPEF_VERSION_METADATA",json.dumps({"version":v,"distribution":d.get("distribution"),"accessLevel":d.get("accessLevel"),"series_last_distribution":series[0]["last"].get("distribution")},sort_keys=True),flush=True)
for x in d.get("distribution",[]):
    for k,val in x.items():
        if "resource" in k.casefold() and isinstance(val,str) and val.startswith("https://data.cms.gov/"):
            try:
                r=registry.get_json(val)
                print("PPEF_RESOURCE_METADATA",json.dumps({"field":k,"url":val,"response":r},sort_keys=True)[:20000],flush=True)
            except Exception as e:print("PPEF_RESOURCE_ERROR",k,type(e).__name__,flush=True)
rows,_=il_records("hospitals")
for k in ("entity_id","local_id","mpn_id","closed_date"):
    counts=Counter()
    for r in rows:
        v=r.get(k)
        if v is None or v=="":s="missing"
        elif re.fullmatch(r"[0-9]{1,20}",str(v)):s="numeric"
        else:s="shape:"+re.sub(r"[A-Za-z]","A",re.sub(r"[0-9]","9",str(v)))[:40]
        counts[s]+=1
    print("IL_FIELD_SHAPE",k,json.dumps(counts),flush=True)
