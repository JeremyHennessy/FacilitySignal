"""Crosswalk Q3 2026 POS headers to exact 2023 publisher layout references.

These PDF layouts are historical, not contemporary field/domain approval.
Keep provider category and page location; never apply a category's meaning
to another category. No provider records are downloaded or emitted.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from collect_registry import response
from pos_raw_field_profile import read, need, INVENTORY

URLS={
"qies":"https://data.cms.gov/sites/default/files/2023-07/0ca58d5d-7914-4532-b22d-41741d3e6151/P.QWB.POSQ.OTHER.LAYOUT.MAR23.pdf",
"clia":"https://data.cms.gov/sites/default/files/2023-07/50eacc07-7930-4e62-97e3-e04a2dc1e2a3/P.QWB.POSQ.CLIA.LAYOUT.MAR23.pdf"
}
QIES_HASH="08291e4cd5d0221b1201d48be1d58a916af9ea4b608b90c4ebc5ae450ef1f4b7"
SAS=re.compile(r"^\s*SAS Name:\s*([A-Za-z0-9_]+)\s*$",re.I)
CATEGORY=re.compile(r'^\s*(.+?),\s*CATEGORY\s*=\s*"([0-9]+)"',re.I)
PAGE=re.compile(r"^\s*PAGE:\s*(\d+)\s*$",re.I)
RECORD=re.compile(r"^\s*(\S.*?)\s{2,}(\d{1,4})\s+(\d{1,5})\s+(\d{1,5})(?:\s+(VARCHAR2|CHAR|NUMBER|DATE|FLOAT|INTEGER|DECIMAL))?\s*$",re.I)
DESC=re.compile(r"^\s*Description:\s*(.*)$",re.I)
CODE=re.compile(r"^\s*(?:VALUES:\s*)?([A-Za-z0-9]+)\s*=\s*(.+)$",re.I)
TYPE=re.compile(r"^\s*(VARCHAR2|CHAR|NUMBER|DATE|FLOAT|INTEGER|DECIMAL)\s*$",re.I)

def retrieve(source,path):
    h=hashlib.sha256()
    size=0
    with response(URLS[source],"application/pdf") as src,path.open("xb") as dst:
        need(src.geturl()==URLS[source],"publisher PDF redirect changed")
        while chunk:=src.read(1024*1024):
            size+=len(chunk)
            need(size<=20_000_000,"layout exceeds bound")
            h.update(chunk)
            dst.write(chunk)
    need(path.read_bytes()[:5]==b"%PDF-","not a PDF")
    if source=="qies":
        need(h.hexdigest()==QIES_HASH,"previously qualified QIES layout hash changed")
    return {"url":URLS[source],"sha256":h.hexdigest(),"bytes":size,"document_date":"2023-04-02"}

def clean(s):
    return " ".join(s.split())

def parse(text):
    result=defaultdict(list)
    category=None
    printed=None
    rec=None
    active=None
    categories={}
    for physical,content in enumerate(text.split("\f"),1):
        for line in content.splitlines():
            c=CATEGORY.match(line)
            if c:
                label,code=clean(c.group(1)),c.group(2)
                category=code
                categories.setdefault(code,set()).add(label)
                continue
            p=PAGE.match(line)
            if p:
                printed=int(p.group(1))
                continue
            if ("POS RECORD LAYOUT" in line or "SHORT DESCRIPTION" in line or
                    "FILE CREATION DATE" in line or line.strip() in ("TYPE","")):
                continue
            m=RECORD.match(line)
            if m:
                label,length,start,end,typ=m.groups()
                # Layout position consistency filters spurious numeric lines.
                if int(end)-int(start)+1==int(length):
                    rec={"label":clean(label),"length":int(length),"start":int(start),
                         "end":int(end),"type":typ,"description_parts":[],"describing":False}
                    active=None
                    continue
            d=DESC.match(line)
            if d:
                if rec is None:
                    rec={"label":None,"length":None,"start":None,"end":None,
                         "type":None,"description_parts":[],"describing":False}
                rec["description_parts"]=[d.group(1)] if d.group(1) else []
                rec["describing"]=True
                continue
            s=SAS.match(line)
            if s:
                key=s.group(1).upper()
                item={"category_code":category,"printed_page":printed,"physical_pdf_page":physical,
                      "label_candidate":None,"description_candidate":None,"type_candidate":None,
                      "layout_length":None,"layout_start":None,"layout_end":None,"code_examples":[]}
                if rec:
                    item.update(label_candidate=rec["label"],
                                description_candidate=clean(" ".join(rec["description_parts"])) or None,
                                type_candidate=rec["type"],layout_length=rec["length"],
                                layout_start=rec["start"],layout_end=rec["end"])
                result[key].append(item)
                active=item
                rec=None
                continue
            if rec:
                typ=TYPE.match(line)
                if typ and not rec["describing"]:
                    rec["type"]=typ.group(1).upper()
                elif rec["describing"] and "COBOL Name:" not in line and "VALUES:" not in line:
                    # Avoid copying header artifacts. Candidates require later review.
                    rec["description_parts"].append(line.strip())
                elif not rec["describing"] and rec["label"] and line.strip():
                    rec["label"]+=" "+line.strip()
            if active:
                match=CODE.match(line)
                if match and len(active["code_examples"])<160:
                    active["code_examples"].append([match.group(1),clean(match.group(2))])
    return dict(result),{k:sorted(v) for k,v in categories.items()}

def crosswalk(source,parsed,categories,inventory,meta):
    rows=[]
    for f in inventory["fields"]:
        matches=parsed.get(f["field"].upper(),[])
        groups=defaultdict(list)
        for m in matches:
            signature=(m["label_candidate"],m["description_candidate"],m["type_candidate"])
            groups[signature].append(m)
        definitions=[]
        for (label,desc,typ),occ in groups.items():
            definitions.append({"label_candidate":label,"description_candidate":desc,
                "type_candidate":typ,"occurrences":[{k:v for k,v in x.items()
                    if k not in ("label_candidate","description_candidate","type_candidate")} for x in occ]})
        rows.append({"ordinal":f["ordinal"],"field":f["field"],
            "historical_name_matches":len(matches),"distinct_candidate_definitions":len(groups),
            "status":"historical_candidate_only" if matches else "no_historical_exact_name_match",
            "definitions":definitions})
    known={"qies":["PRVDR_NUM","CLIA_ID_NUMBER_1","CT_SCAN_SRVC_CD","CRDC_CTHRTZTN_PRCDR_ROOMS_CNT"],
           "clia":["PRVDR_NUM","CRTFCT_TYPE_CD","FORM_116_TEST_VOL_CNT","WVD_TEST_VOL_CNT"]}[source]
    for field in known:
        scope="01" if source=="qies" else "22"
        need(any(m["category_code"]==scope and m["description_candidate"] for m in parsed.get(field,[])),
             "known historical reference not recovered: "+field)
    return {"format_version":1,"source":source,"current_release":inventory["period"],
            "source_sha256":inventory["source_sha256"],"historical_layout":meta,
            "provider_categories":categories,"raw_fields":len(rows),
            "fields_with_exact_historical_match":sum(bool(f["historical_name_matches"]) for f in rows),
            "fields_with_candidate_description":sum(any(x["description_candidate"] for x in f["definitions"]) for f in rows),
            "unmatched_fields":[f["field"] for f in rows if not f["historical_name_matches"]],
            "fields_with_multiple_candidate_definitions":sum(f["distinct_candidate_definitions"]>1 for f in rows),
            "historical_occurrences":sum(f["historical_name_matches"] for f in rows),
            "fields":rows,"limitations":["Publisher catalog links a historical April 2023 layout; not proof of Q3 2026 semantics.",
                "Page-based extracted text and codes are review candidates; scope, formatting and current value domains must be verified.",
                "Different provider categories can assign different domains. Never infer assets, current status or legal ownership."]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",choices=sorted(URLS),required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    need(not a.output.exists(),"new output required")
    inv=read(INVENTORY)["registries"][a.source]
    with tempfile.TemporaryDirectory(prefix="legacy-pos-layout-") as tmp:
        path=Path(tmp)/"layout.pdf"
        meta=retrieve(a.source,path)
        extracted=subprocess.run(["pdftotext","-layout",str(path),"-"],check=True,capture_output=True,
                                 timeout=120).stdout.decode("utf-8",errors="strict")
        need(len(extracted)<=30_000_000,"layout extraction exceeds bound")
        parsed,categories=parse(extracted)
        result=crosswalk(a.source,parsed,categories,inv,meta)
    with a.output.open("x",encoding="utf-8") as f:
        json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print("LEGACY_LAYOUT_SUMMARY",json.dumps({k:v for k,v in result.items() if k!="fields"},sort_keys=True),flush=True)
    # Compact evidence rows: full candidate text, code examples and positions
    # remain in aggregate metadata artifact, not in repetitive logs.
    for f in result["fields"]:
        compact={k:v for k,v in f.items() if k!="definitions"}
        compact["definitions"]=[{"label_candidate":d["label_candidate"],
             "description_candidate":d["description_candidate"],"type_candidate":d["type_candidate"],
             "locations":[[o["category_code"],o["physical_pdf_page"],o["printed_page"]]
                          for o in d["occurrences"]]} for d in f["definitions"]]
        print("LEGACY_LAYOUT_FIELD",json.dumps(compact,separators=(",",":"),sort_keys=True),flush=True)

if __name__=="__main__":
    main()
