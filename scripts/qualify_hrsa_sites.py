"""Bounded HRSA public site release schema and privacy-safe aggregate qualification.
No institutional addresses, names, coordinates, individual identifiers or shelter records
are retained. Explicit field semantics review precedes any row-level integration.
"""
import argparse,csv,hashlib,io,json,re,urllib.request,zipfile
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import openpyxl

ROOT="https://data.hrsa.gov/DataDownload/DD_Files/"
CSV=ROOT+"Health_Center_Service_Delivery_and_LookAlike_Sites.csv"
META=ROOT+"EHB_SITE_DATAMART_METADATA.XLSX"
ALLOWED={CSV,META}

def require(ok,message):
    if not ok:raise ValueError(message)

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        require(newurl in ALLOWED,"unexpected redirect")
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def retrieve(url,limit):
    require(url in ALLOWED,"unapproved URL")
    req=urllib.request.Request(url,headers={"User-Agent":"FacilitySignal institutional source qualification","Accept":"*/*"})
    with urllib.request.build_opener(Redirect()).open(req,timeout=60) as res:
        require(res.geturl()==url,"unexpected response URL")
        data=res.read(limit+1)
        require(0<len(data)<=limit,"download size bound")
        return data,{"url":url,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),
                    "last_modified":res.headers.get("Last-Modified"),"etag":res.headers.get("ETag"),
                    "retrieved_at":datetime.now(timezone.utc).isoformat()}

def norm(s):
    return re.sub(r"[^a-z0-9]+"," ",str(s).casefold()).strip()

def dictionary(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        require(sum(x.file_size for x in z.infolist())<=10_000_000 and len(z.infolist())<=100,"metadata expansion bound")
    book=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=True,keep_links=False)
    cells=set();sheets=[]
    try:
        for sheet in book:
            sheet.reset_dimensions();count=0
            for row in sheet.iter_rows(values_only=True):
                count+=1
                require(count<=2000 and len(row)<=100,"metadata dimensions bound")
                for v in row:
                    if isinstance(v,str):cells.add(norm(v))
            sheets.append({"rows":count})
    finally:book.close()
    return cells,sheets

# Candidate header labels, never silently pick among multiple matches.
ALIASES={"site_id":{"bphc assigned number","bphc assigned site number","bphc site number"},
         "site_address":{"site address","site street address"},
         "site_zip":{"site postal code","site zip","site zip code"},
         "site_type":{"site type","health center location type description"},"location_setting":{"location setting","site location setting","health center service delivery site location setting description"},
         "site_state":{"site state","site state abbreviation","site state code"},
         "site_status":{"site status","site status description"},"center_type":{"health center type"},
         "record_date":{"data warehouse record create date","record date"}}
def resolve(headers):
    out={}
    for key,aliases in ALIASES.items():
        candidates=[h for h in headers if norm(h) in aliases]
        if len(candidates)==1:out[key]=candidates[0]
    return out

def audit(data,metadata_cells):
    reader=csv.DictReader(io.StringIO(data.decode("utf-8-sig"),newline=""),strict=True)
    headers=reader.fieldnames or []
    require(0<len(headers)<=150 and len(set(headers))==len(headers),"invalid CSV header")
    # The live export has one empty final header. Preflight every row locally.
    # Accept only exact named-column width, or exactly one additional empty cell;
    # never discard a populated extra cell or pad a missing named field.
    header_repair=None
    if headers[-1]=="" and all(norm(h) for h in headers[:-1]) and len(resolve(headers[:-1]))>=3:
        named=headers[:-1]
        raw=csv.reader(io.StringIO(data.decode("utf-8-sig"),newline=""),strict=True)
        next(raw)
        widths=Counter();bad=0;populated_extra=0
        for values in raw:
            widths[str(len(values))]+=1
            require(sum(widths.values())<=100000,"row count bound")
            if len(values)==len(named)+1 and values[-1]!="":populated_extra+=1
            if not (len(values)==len(named) or (len(values)==len(named)+1 and values[-1]=="")):bad+=1
        header_repair={"original_columns":len(headers),"named_columns":len(named),"row_width_counts":dict(widths),
                       "unexpected_width_or_nonempty_extra_rows":bad,"populated_extra_rows":populated_extra}
        if bad==0 and sum(widths.values())>0:
            headers=named
            raw=csv.reader(io.StringIO(data.decode("utf-8-sig"),newline=""),strict=True)
            next(raw)
            reader=(dict(zip(headers,values[:len(headers)],strict=True)) for values in raw)
    # Publisher labels can contain Unicode punctuation or formatting whitespace.
    # Require bounded, nonempty labels and unique normalized names. Confirm
    # multiple institutional field anchors before retaining any header text.
    # Preserve structural failure evidence even when no data can be screened.
    # Empty, malformed and unverified columns are never accepted or printed.
    invalid=[]
    for i,h in enumerate(headers):
        reasons=[]
        if not norm(h):reasons.append("empty_or_no_ascii_alphanumeric")
        if len(h)>150:reasons.append("length_bound")
        if any(not c.isprintable() and c not in "\t\r\n" for c in h):reasons.append("nonprinting")
        if reasons:invalid.append({"column_ordinal":i+1,"length":len(h),"reasons":reasons})
    normalized_unique=len({norm(h) for h in headers})==len(headers)
    if invalid or not normalized_unique:
        count=0;shape_errors=0;nonblank_invalid=Counter()
        for row in reader:
            count+=1
            require(count<=100000,"row count bound")
            if None in row or any(v is None for v in row.values()):
                shape_errors+=1;continue
            for col in invalid:
                i=col["column_ordinal"]-1
                if row[headers[i]].strip():nonblank_invalid[str(i+1)]+=1
        return {"headers":[],"columns":len(headers),"resolved_candidate_fields":{},
                "metadata_exact_header_matches":sum(norm(h) in metadata_cells for h in headers),
                "header_repair":header_repair,"header_structure":{"invalid_columns":invalid,"normalized_unique":normalized_unique,
                    "row_shape_errors":shape_errors,"invalid_column_nonblank_counts":dict(nonblank_invalid)},
                "input_rows":count,"mapping_complete":False,"privacy_screened_rows":0,
                "excluded_protected_or_incomplete_rows":0,"missing_site_id":0,"duplicate_site_id":0,
                "retained_row_level_records":0,"limits":"Structural failure diagnostic only; no source headers or row values retained."}
    mapped=resolve(headers)
    anchors=sum(k in mapped for k in ("site_id","site_address","site_zip","site_type","site_state","site_status","location_setting"))
    report={"headers":headers if anchors>=3 else [],"columns":len(headers),"resolved_candidate_fields":mapped if anchors>=3 else {},
            "header_repair":header_repair,"header_anchors":anchors,"metadata_exact_header_matches":sum(norm(h) in metadata_cells for h in headers)}
    total=0;excluded=0;accepted=0;missing_id=0;duplicates=0;seen=set();status=Counter()
    required={"site_id","site_address","site_zip","site_type","location_setting","site_state","site_status"}
    ready=required<=mapped.keys() and anchors>=3
    for row in reader:
        total+=1
        require(total<=100000 and None not in row and all(v is not None for v in row.values()),"CSV row shape or count bound")
        if not ready:continue
        # Conservative suppression: exclude any incomplete site address/ZIP, any
        # shelter or domestic-violence descriptor anywhere in the row, and any
        # missing site type or location setting. Never retain excluded identities.
        if (any(norm(row[mapped[k]]) in {"","na","n a","not available","not applicable","unknown","suppressed","redacted","null","none"} for k in ("site_address","site_zip","site_type","location_setting"))
            or any(re.search(r"shelter|domestic[ _-]*violence|battered",v,re.I) for v in row.values())):
            excluded+=1;continue
        key=row[mapped["site_id"]].strip()
        if not key:missing_id+=1;continue
        if key in seen:duplicates+=1;continue
        seen.add(key);accepted+=1
        # Do not emit arbitrary publisher text or site/geographic distributions.
        s=norm(row[mapped["site_status"]])
        status[s if s in {"active","inactive","closed","open","planned","pending"} else "other_or_blank"]+=1
    require(total>0,"empty source")
    report.update({"input_rows":total,"mapping_complete":ready,"missing_required_mapping":sorted(required-mapped.keys()),
                   "privacy_screened_rows":accepted,"excluded_protected_or_incomplete_rows":excluded,
                   "missing_site_id":missing_id,"duplicate_site_id":duplicates,"status_counts":dict(status),
                   "retained_row_level_records":0,
                   "limits":"Candidate mapping only. No location or identity retained, no protected record linkage, no current operation inference. Metadata semantic and suppression review required before commercial row-level projection."})
    if ready:require(total==excluded+accepted+missing_id+duplicates and sum(status.values())==accepted,"reconciliation failed")
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    meta,m=retrieve(META,1_000_000)
    cells,sheets=dictionary(meta)
    data,source=retrieve(CSV,35_000_000)
    result=audit(data,cells)
    result.update({"source":source,"dictionary":m,"metadata_sheets":sheets,
                   "publisher_catalog":"https://catalog.data.gov/dataset/health-center-service-delivery-and-lookalike-sites",
                   "reuse":"Publisher lists public domain/CC0 and no usage limitations; protected records excluded; commercial projection requires semantic review."})
    a.audit.parent.mkdir(parents=True,exist_ok=True)
    with a.audit.open("x") as f:json.dump(result,f,indent=2);f.write("\n")
    print("HRSA_SITE_AUDIT",json.dumps(result),flush=True)
    require(result["mapping_complete"],"candidate header mapping incomplete; review aggregate header")
    require(result["privacy_screened_rows"]>0 and result["missing_site_id"]==result["duplicate_site_id"]==0,"candidate identifier anomalies require review")
if __name__=="__main__":main()
