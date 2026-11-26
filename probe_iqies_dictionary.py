"""Inspect the publisher's exact iQIES dictionary, without downloading provider rows."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import tempfile
from datetime import datetime,timezone
import zipfile
import openpyxl
from collect_registry import response
from probe_pos_fields import INVENTORY,verify_inventory
from iqies_full_dictionary import extract as extract_full_dictionary

URL="https://data.cms.gov/sites/default/files/2026-11/dd404bad-f893-4c80-b472-ab600bee1405/iQIES%20POS%20Data%20Dictionary%20Oct2026.xlsx"
MAX_BYTES=20_000_000
MAX_EXPANDED=100_000_000
MAX_CELLS=1_000_000
PRIORITY={"prvdr_type_id","prvdr_sbtyp_id","fed_crtfctn_stus_id","fed_crtfctn_stus_name","cmplnc_stus_cd","pgm_trmntn_cd","trmntn_exprtn_dt","oprtg_room_cnt","procedure_room_cnt","dlys_stn_cnt","bed_cnt","crtfd_bed_cnt","lab_srvc_cd","rdlgy_srvc_cd","phrmcy_srvc_cd","dntl_srgry_sw","endscpy_srgry_sw","lsc_wvr_sw","home_trng_sprt_only_srvc_sw","hmdlys_srvc_sw","prtnl_dlys_srvc_sw","nrsng_srvc_cntrctr_sw","acrdtn_type_cd"}

def need(condition,message):
    if not condition: raise ValueError(message)

def download(path):
    size=0; h=hashlib.sha256()
    with response(URL,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") as src,path.open("xb") as dst:
        need(src.geturl()==URL,"unexpected dictionary redirect")
        while chunk:=src.read(1024*1024):
            size+=len(chunk);need(size<=MAX_BYTES,"dictionary download limit")
            h.update(chunk);dst.write(chunk)
    need(size>0,"empty dictionary")
    return {"url":URL,"sha256":h.hexdigest(),"bytes":size,"retrieved_at":datetime.now(timezone.utc).isoformat()}

def inspect(path,fields):
    need(zipfile.is_zipfile(path),"not XLSX")
    with zipfile.ZipFile(path) as z:
        need(sum(i.file_size for i in z.infolist())<=MAX_EXPANDED,"expanded dictionary limit")
        need("xl/workbook.xml" in z.namelist(),"not workbook")
    lookup={f.casefold():f for f in fields}
    need(len(lookup)==len(fields),"ambiguous expected fields")
    matches=defaultdict(list); sheets=[]; cells=0
    book=openpyxl.load_workbook(path,read_only=True,data_only=True,keep_links=False)
    try:
        for sheet in book.worksheets:
            sheet.reset_dimensions(); nonempty=0; maxwidth=0; columns=Counter()
            previews=[]
            for n,row in enumerate(sheet.iter_rows(values_only=True),1):
                cells+=len(row);need(cells<=MAX_CELLS,"dictionary cell limit")
                values=[(i+1,str(v).strip()) for i,v in enumerate(row) if v is not None and str(v).strip()]
                if not values: continue
                nonempty+=1;maxwidth=max(maxwidth,len(row))
                # Only dictionary metadata, never a provider data sample. Record location, not all prose.
                if len(previews)<4:
                    previews.append({"row":n,"cells":[{"column":i,"text":v[:120]} for i,v in values[:12]]})
                for col,value in values:
                    key=value.casefold()
                    if key in lookup:
                        columns[col]+=1
                        entry={"sheet":sheet.title,"row":n,"column":col,"exact_spelling":value}
                        if key in PRIORITY:
                            entry["context_columns"]=[{"column":i,"text":v[:500]} for i,v in values if i!=col][:14]
                        matches[lookup[key]].append(entry)
            sheets.append({"sheet":sheet.title,"nonempty_rows":nonempty,"max_row_width":maxwidth,"exact_match_columns":dict(columns),"opening_rows":previews})
    finally:
        book.close()
    found=sorted(matches); missing=sorted(set(fields)-set(found))
    return {"expected_fields":len(fields),"matched_fields":len(found),"missing_fields":missing,
            "ambiguous_fields":sorted(f for f,m in matches.items() if len(m)>1),"sheets":sheets,
            "field_locations":dict(matches),"semantic_status":"unreviewed",
            "limitations":["Exact cell text match is not an accepted definition, mapping or code interpretation.","Multiple matches require human review; missing matches are not filled by guessing."]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    need(not a.audit.exists(),"audit already exists")
    inv=verify_inventory(json.loads(INVENTORY.read_text()))
    fields=[f["field"] for f in inv["registries"]["iqies"]["fields"]]
    with tempfile.TemporaryDirectory(prefix="iqies-dictionary-") as tmp:
        path=Path(tmp)/"dictionary.xlsx"; meta=download(path)
        audit=inspect(path,fields)
        full=extract_full_dictionary(path,fields)
    result={"source":meta,"schema_audit":45686866946,"inventory_source":inv["registries"]["iqies"]["version_api"],**audit}
    result["full_dictionary_metadata"]=full
    a.audit.parent.mkdir(parents=True,exist_ok=True);a.audit.write_text(json.dumps(result,indent=2)+"\n")
    print("IQIES_DICTIONARY_SUMMARY",json.dumps({k:v for k,v in result.items() if k not in ("field_locations","full_dictionary_metadata")}),flush=True)
    for field in sorted(PRIORITY):
        locations=audit["field_locations"].get(field,[])
        if locations: print("IQIES_DICTIONARY_FIELD",field,json.dumps(locations),flush=True)
    print("IQIES_FULL_SUMMARY",json.dumps({k:v for k,v in full.items() if k not in ("fields","mapping_sheets")}),flush=True)
    for field in full["fields"]:
        print("IQIES_FULL_FIELD",json.dumps(field),flush=True)
    for key,table in full["mapping_sheets"].items():
        print("IQIES_FULL_MAPPING",key,json.dumps(table),flush=True)
    need(audit["matched_fields"]>0,"no exact dictionary matches")
if __name__=="__main__":main()
