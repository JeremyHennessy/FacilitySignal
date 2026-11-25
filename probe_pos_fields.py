"""Inspect pinned CMS POS API schemas and official documentation references.

Never download full registry payloads or print any row values. One sample per registry
only, for column comparison. Definitions/code domains remain unverified.
"""
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
from collect_registry import CATALOG,TITLES,get_json,allowed,expected_rows
from build_combined import require

ROOT=Path(__file__).resolve().parent
INVENTORY=ROOT/"research"/"pos_field_inventory_q3_2026.json"

def verify_inventory(inventory):
    require(set(inventory["registries"])==set(TITLES),"registry scope")
    for key,expected in (("qies",473),("iqies",186),("clia",103)):
        entry=inventory["registries"][key]
        fields=entry["fields"]
        require(len(fields)==expected,"field count mismatch "+key)
        require([x["ordinal"] for x in fields]==list(range(1,expected+1)),"ordinal mismatch")
        require(len({x["field"].casefold() for x in fields})==expected,"ambiguous field")
        require(all(x["semantic_status"]=="dictionary_pending" and x["publication"]=="not_approved" for x in fields),"unreviewed semantic assertion")
        allowed(entry["version_api"])
    return inventory

def docs_for(entry):
    # Catalog-provided resource metadata only. Do not guess URLs or traverse unrelated domains.
    result=[]
    for k in ("references","describedBy","landingPage"):
        value=entry.get(k)
        values=value if isinstance(value,list) else [value]
        for v in values:
            if isinstance(v,str) and v.startswith("https://data.cms.gov/"):
                result.append({"metadata_field":k,"url":allowed(v)})
    for d in entry.get("distribution",[]):
        fmt=str(d.get("format","")).upper()
        title=str(d.get("title") or d.get("description") or "")
        if fmt in ("PDF","XLS","XLSX","HTML","DOC","DOCX") or "dictionary" in title.lower() or "methodology" in title.lower():
            url=d.get("downloadURL") or d.get("accessURL")
            if isinstance(url,str) and url.startswith("https://data.cms.gov/"):
                result.append({"metadata_field":"distribution","url":allowed(url),"format":fmt,"title":title[:200]})
    return result

def reconcile(fields,sample):
    require(isinstance(sample,list) and len(sample)==1 and isinstance(sample[0],dict),"unexpected API sample response")
    csv={x["field"].casefold() for x in fields};api={x.casefold() for x in sample[0]}
    require(len(api)==len(sample[0]),"duplicate API columns")
    return {"csv_columns":len(csv),"api_columns":len(api),"csv_only":sorted(csv-api),"api_only":sorted(api-csv),"exact_normalized_schema":csv==api}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    inventory=verify_inventory(json.loads(INVENTORY.read_text()))
    catalog=get_json(CATALOG)
    out={"retrieved_at":datetime.now(timezone.utc).isoformat(),"registries":{},"limitations":["No bulk registry download, source row values or interpreted capabilities.","API sample is schema evidence only; official codebooks and applicability review remain required."]}
    for key,title in TITLES.items():
        matches=[d for d in catalog["dataset"] if d.get("title")==title]
        require(len(matches)==1 and matches[0].get("accessLevel")=="public","catalog identity")
        entry=inventory["registries"][key]
        api=entry["version_api"]
        count=expected_rows({"api":api})
        require(count==entry["source_rows"],"pinned API count drift")
        stats=reconcile(entry["fields"],get_json(api+"?size=1"))
        out["registries"][key]={"api":api,"row_count":count,**stats,"catalog_documentation_candidates":docs_for(matches[0]),"catalog_metadata_keys":sorted(matches[0]),"dictionary_status":"unverified"}
        print("POS_SCHEMA_AUDIT",key,json.dumps(out["registries"][key]),flush=True)
    a.audit.parent.mkdir(parents=True,exist_ok=True);a.audit.write_text(json.dumps(out,indent=2)+"\n")
    require(all(x["exact_normalized_schema"] for x in out["registries"].values()),"API/CSV schema differences require review")
if __name__=="__main__":main()
