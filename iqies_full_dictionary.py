"""Read full publisher dictionary metadata, not provider records.

Keep each source cell and scope intact. This extraction establishes dictionary
evidence, not observed source domains, normalized facts or publication approval.
"""
from collections import defaultdict
import hashlib
from pathlib import Path
import zipfile
import openpyxl

PINNED_SHA = "bd68d76dc72ee5c3b3249c459644ff2ed90c8e8cf6e182b76742ec53164c0594"
PINNED_BYTES = 40305
HEADER = ("POS Header", "iQIES Data Format", "Description", "Definition",
          "Applicable Provider Types", "Mapping")
TABLES = {"M"+str(i) for i in range(1,13)}
MAX_CELLS = 100000
MAX_TEXT = 10000

def need(condition, message):
    if not condition:
        raise ValueError(message)

def cell(value):
    if value is None:
        return None
    need(type(value) in (str, int, float, bool), "unsupported dictionary cell type")
    result = str(value)
    need(len(result) <= MAX_TEXT, "dictionary cell exceeds bound")
    return result

def read_rows(sheet, limit):
    sheet.reset_dimensions()
    result = []
    cells = 0
    for rownum, row in enumerate(sheet.iter_rows(values_only=True), 1):
        cells += len(row)
        need(cells <= MAX_CELLS and rownum <= limit, "dictionary sheet exceeds bounds")
        values = tuple(cell(v) for v in row)
        if not any(v is not None and v.strip() for v in values):
            continue
        while values and (values[-1] is None or not values[-1].strip()):
            values = values[:-1]
        result.append((rownum, values))
    return result

def extract(path, fields, pinned=True):
    path = Path(path)
    need(len(fields)==len({f.casefold() for f in fields}), "ambiguous source field list")
    if pinned:
        need(path.stat().st_size==PINNED_BYTES, "unexpected dictionary bytes")
        need(hashlib.sha256(path.read_bytes()).hexdigest()==PINNED_SHA,
             "dictionary release changed")
        need(len(fields)==186, "unexpected source schema count")
    need(zipfile.is_zipfile(path), "invalid workbook")
    with zipfile.ZipFile(path) as z:
        need(sum(i.file_size for i in z.infolist())<=100000000, "expanded dictionary limit")
        need("xl/workbook.xml" in z.namelist(), "not workbook")
    book = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        need(set(book.sheetnames)==TABLES|{"POS Data Dictionary"}, "unexpected dictionary sheets")
        sheets={}
        for sheetname in sorted(TABLES, key=lambda name:int(name[1:])):
            rows=read_rows(book[sheetname],10000)
            need(bool(rows) and rows[0][0]==1, "missing domain header")
            header=rows[0][1]
            need(header[:2]==("ID","Value") and (len(header)==2 or (
                len(header)==3 and header[2] in ("Provider Type","Provider Types")
            )), "unexpected domain header")
            entries=[]
            for ordinal, row in rows[1:]:
                need(len(row)<=len(header), "unexpected mapping columns")
                vals=row+(None,)*(len(header)-len(row))
                # Blank or duplicate code/label rows remain evidence, not silently dropped.
                entries.append({"row":ordinal,"code":vals[0],"label":vals[1],
                                "provider_types":vals[2] if len(vals)==3 else None})
            sheets[sheetname]={"header":list(header),"entries":entries,
                               "status":"publisher_mapping_rows_extracted_not_domain_qualified"}
        rows=read_rows(book["POS Data Dictionary"],1000)
        need(bool(rows) and rows[0]==(1,HEADER), "unexpected dictionary header")
        lookup=defaultdict(list)
        for ordinal,row in rows[1:]:
            need(len(row)<=len(HEADER), "unexpected dictionary columns")
            name,fmt,label,definition,scope,mapping=row+(None,)*(len(HEADER)-len(row))
            need(name is not None and name.strip(), "unnamed dictionary row")
            lookup[name.strip().casefold()].append({
                "row":ordinal,"publisher_header":name,"format":fmt,"label":label,
                "definition":definition,"applicability":scope,"mapping_raw":mapping,
                "mapping_status":"not_specified" if not mapping else (
                    "exact_mapping_sheet_reference" if mapping.strip() in sheets else
                    "unresolved_mapping_reference")
            })
        result=[]
        for ordinal,name in enumerate(fields,1):
            candidates=lookup.get(name.casefold(),[])
            status=("missing" if not candidates else "ambiguous" if len(candidates)>1 else
                    "unique_metadata_match")
            result.append({"ordinal":ordinal,"field":name,"match_status":status,
                           "candidates":candidates,
                           "definition_present":len(candidates)==1 and bool(
                               candidates[0]["definition"] and candidates[0]["definition"].strip()),
                           "scope_present":len(candidates)==1 and bool(
                               candidates[0]["applicability"] and candidates[0]["applicability"].strip()),
                           "semantic_status":"publisher_metadata_extracted_not_full_semantic_review",
                           "raw_value_profile":"pending"})
        source_names={name.casefold() for name in fields}
        missing=[f["field"] for f in result if f["match_status"]=="missing"]
        ambiguous=[f["field"] for f in result if f["match_status"]=="ambiguous"]
        if pinned:
            need(missing==["fed_fundd_fqhc_sw"] and ambiguous==["physn_arngmt_sw"],
                 "pinned dictionary reconciliation changed")
        return {"source_fields":len(fields),"dictionary_rows":len(rows)-1,
                "unique_matches":sum(f["match_status"]=="unique_metadata_match" for f in result),
                "unique_with_definition":sum(f["definition_present"] for f in result),
                "unique_with_scope":sum(f["scope_present"] for f in result),
                "missing_fields":missing,"ambiguous_fields":ambiguous,
                "unmatched_dictionary_rows":[row for k,rr in lookup.items()
                                             if k not in source_names for row in rr],
                "mapping_sheet_count":len(sheets),
                "mapping_row_count":sum(len(s["entries"]) for s in sheets.values()),
                "fields":result,"mapping_sheets":sheets}
    finally:
        book.close()
