"""Qualify remaining posted NPPES weekly files and monthly deactivation list.

No monthly archive retrieval, no status application, no individual NPI retention.
Deactivation list includes individuals and organizations without a type field:
validate its syntax and dates, never link former identities or store its keys.
"""
import argparse,csv,io,json,re,tempfile,zipfile
from collections import Counter
from datetime import date,datetime
from pathlib import Path,PurePosixPath
from contextlib import closing
import openpyxl
from scripts.qualify_nppes_v2 import download,inspect,npi_valid,date_state
from build_combined import require

LABELS={
 "week_1102":"NPPES Data Dissemination V.2 - Weekly Update - 110226_110826",
 "week_1109":"NPPES Data Dissemination V.2 - Weekly Update - 110926_111526",
 "deactivation":"NPPES Data Dissemination V.2 - Monthly Deactivation Update - November 09, 2026",
}
DATE_HEADERS={"npideactivationdate","deactivationdate"}
DEACTIVATION_PIN="3bc64ebb331b72d2fc80a15c4b4a89d57810c69991b33985c5bc31b763504190"
MAX_DEACTIVATION_ROWS=2_000_000
MAX_DEACTIVATION_EXPANDED=200_000_000

def norm(v):return re.sub(r"[\s_-]+","",str(v or "").strip().casefold())
def date_bucket(v):
    if isinstance(v,datetime):d=v.date()
    elif isinstance(v,date):d=v
    else:
        s=str(v or "").strip()
        if not s:return "blank"
        try:
            if re.fullmatch(r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}",s):d=datetime.strptime(s,"%m/%d/%Y").date()
            elif re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",s):d=date.fromisoformat(s)
            else:return "unrecognized"
        except ValueError:return "invalid"
    return "after_release" if d>date(2026,11,9) else "on_or_before_release"

def scan_deactivation(reader):
    # The publisher's actual first record has one 43-character cell.
    # Only skip a bounded recognizable report title or empty rows; never
    # discard arbitrary data rows or a second table before the header.
    recognized={"npi","npideactivationdate","deactivationdate","npinumber","npiid","deactivationdt","npideactivationdt"}
    h=None;header_ordinal=0;preamble=Counter()
    for i,header in enumerate(reader,1):
        require(i<=10,"deactivation header not recognized")
        h0=[norm(x) for x in header]
        structure=[{"column":j+1,"recognized_label":v if v in recognized else None,"length":len(str(raw or "")),
                    "shape":"text" if isinstance(raw,str) and re.fullmatch(r"[A-Za-z _-]{1,100}",raw) else "other"} for j,(raw,v) in enumerate(zip(header,h0))]
        print("NPPES_DEACTIVATION_SCHEMA",json.dumps({"row_ordinal":i,"column_count":len(h0),"columns":structure[:20]},sort_keys=True),flush=True)
        if len(h0)==2 and len(set(h0))==2 and "npi" in h0 and len(set(h0)&DATE_HEADERS)==1:
            h=h0;header_ordinal=i;break
        nonblank=[str(x).strip() for x in header if x is not None and str(x).strip()]
        if not nonblank:preamble["blank"]+=1;continue
        if len(nonblank)==1 and len(nonblank[0])<=200 and re.search(r"\bnpi\b",nonblank[0],re.I) and re.search(r"deactivat",nonblank[0],re.I) and not re.fullmatch(r"[0-9]+",nonblank[0]):
            preamble["recognized_report_title"]+=1;continue
        raise ValueError("deactivation header not recognized")
    require(h is not None,"deactivation header not recognized")
    key_idx=h.index("npi");date_idx=next(i for i,v in enumerate(h) if v in DATE_HEADERS)
    rows=0;keys=Counter();dates=Counter();shapes=Counter()
    for row in reader:
        rows+=1;require(rows<=MAX_DEACTIVATION_ROWS,"deactivation row bound")
        shapes[str(len(row))]+=1
        if len(row)!=2:
            keys["malformed_width"]+=1;dates["malformed_width"]+=1;continue
        # Check a single identifier in memory, without retaining a set or
        # attempting to reconstruct former owner names/types.
        v=row[key_idx]
        n=str(v).strip() if v is not None else ""
        keys["checksum_valid" if npi_valid(n) else "invalid_or_missing"]+=1
        dates[date_bucket(row[date_idx])]+=1
    require(rows>0 and rows==sum(keys.values())==sum(dates.values()),"deactivation row reconciliation")
    return {"input_rows":rows,"columns":2,"header_ordinal":header_ordinal,"preamble_counts":dict(preamble),"width_counts":dict(shapes),"key_validation_counts":dict(keys),
            "deactivation_date_states":dict(dates),"distinct_key_count":None,
            "entity_type_available":False,"retained_identifiers":0,
            "limits":"Deactivation list includes both entity types without entity type attribution. No duplicate-key test or identity linkage performed. Count comparison to monthly file is not record-level reconciliation."}

def inspect_deactivation(path):
    with zipfile.ZipFile(path) as z:
        members=[i for i in z.infolist() if not i.is_dir()]
        require(0<len(members)<=20 and sum(i.file_size for i in members)<=MAX_DEACTIVATION_EXPANDED,"deactivation archive bound")
        candidates=[i for i in members if PurePosixPath(i.filename).suffix.casefold() in {".csv",".xlsx"}
                    and "header" not in PurePosixPath(i.filename).stem.casefold()]
        require(len(candidates)==1 and not candidates[0].flag_bits&1,"deactivation data member ambiguous")
        item=candidates[0];fmt=PurePosixPath(item.filename).suffix.casefold()
        if fmt==".csv":
            with z.open(item) as raw,io.TextIOWrapper(raw,encoding="utf-8-sig",newline="",errors="strict") as f:
                result=scan_deactivation(csv.reader(f,strict=True))
        else:
            require(item.file_size<=50_000_000,"nested workbook bound")
            payload=z.read(item)
            with zipfile.ZipFile(io.BytesIO(payload)) as x:
                require(len(x.infolist())<=200 and sum(i.file_size for i in x.infolist())<=MAX_DEACTIVATION_EXPANDED,"nested workbook expansion bound")
            book=openpyxl.load_workbook(io.BytesIO(payload),read_only=True,data_only=True,keep_links=False)
            try:
                require(len(book.worksheets)==1,"unexpected workbook count")
                sheet=book.worksheets[0];sheet.reset_dimensions()
                result=scan_deactivation(sheet.iter_rows(values_only=True))
            finally:book.close()
        result.update({"member_format":fmt,"member_bytes":item.file_size,"member_crc32":format(item.CRC,"08x")})
        return result

def main():
    p=argparse.ArgumentParser();p.add_argument("--audit",type=Path,required=True);p.add_argument("--only",choices=LABELS);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    results={};failures=[]
    # CMS instructs downloading only one file at a time. Use isolated stages
    # sequentially and continue independent checks after a source failure.
    for key,label in LABELS.items():
        if a.only is not None and key!=a.only:continue
        with tempfile.TemporaryDirectory(prefix="nppes-supplement-") as d:
            root=Path(d);path=root/"source.zip";meta=None
            try:
                meta=download(path,"weekly",publisher_label=label)
                if key=="deactivation":require(meta["sha256"]==DEACTIVATION_PIN,"deactivation release changed")
                result=inspect_deactivation(path) if key=="deactivation" else inspect(path,root/"org.sqlite3","weekly")
                result.update({"source_id":"FS-004","scope":key,"publisher_label":label,"publisher":meta,
                               "retained_row_level_records":0,"reuse_review":"pending"})
                if key=="deactivation":
                    result["monthly_untyped_deactivation_rows_comparison"]=360013
                    result["row_count_difference_from_monthly_untyped"]=result["input_rows"]-360013
                    passed=(result["key_validation_counts"]=={"checksum_valid":result["input_rows"]} and
                            result["deactivation_date_states"]=={"on_or_before_release":result["input_rows"]})
                else:
                    c=result["entity_classes"];k=result["organization_key_counts"]
                    passed=(result["distinct_valid_organization_npis"]>0 and not any(c.get(x,0) for x in ("malformed_width","unrecognized_entity_type")) and
                            k.get("invalid_organization_npi",0)==result["duplicate_valid_organization_rows"]==0 and
                            all(not x["key_counts"].get("malformed_width") and not x["key_counts"].get("invalid_key_shape") for x in result["reference_files"].values()))
                result["qualification"]="passed" if passed else "failed"
                if not passed:failures.append(key)
                results[key]=result
                print("NPPES_SUPPLEMENT_SOURCE",key,json.dumps(result,sort_keys=True),flush=True)
            except Exception as e:
                # Report only fixed reason vocabulary and safe publisher metadata.
                known={"exact V2 publisher release link absent or ambiguous","deactivation header not recognized","deactivation release changed","deactivation data member ambiguous","deactivation archive bound","expected V2 archive member absent","unexpected workbook count","deactivation row bound","deactivation row reconciliation","header file shape","separate header disagreement","reference header"}
                result={"scope":key,"publisher_label":label,"qualification":"failed","error_type":type(e).__name__,"reason":str(e) if str(e) in known else "unclassified_failure","publisher":meta,"retained_row_level_records":0}
                results[key]=result;failures.append(key)
                print("NPPES_SUPPLEMENT_SOURCE",key,json.dumps(result,sort_keys=True),flush=True)
    report={"source_id":"FS-004","releases":results,"failed_sources":failures,"monthly_retrieved":False,
            "retained_row_level_records":0,"limits":"Independent release qualification only. No monthly/weekly union, ordered update application, deactivated-identifier linkage, current status inference or persistent integration."}
    with a.audit.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
    print("NPPES_SUPPLEMENTS_AUDIT",json.dumps(report,sort_keys=True),flush=True)
    require(not failures,"supplement source exceptions")
if __name__=="__main__":main()
