"""Diagnose rejected provider-key shapes on the exact previously examined release.

Aggregate fixed shape categories only; no provider values, raw rows, names or
locations are emitted. No acceptance policy is changed.
"""
import argparse,hashlib,json,re,tempfile
from collections import Counter
from pathlib import Path
from contextlib import closing
import openpyxl
from scripts.qualify_qcor_expansion import download,provider_key,MAX_ROWS
from scripts.qualify_qcor_provider import map_header
from build_combined import require

PINS={
 "rhc":("6bc5ea259da6149770068d823f8223704e05e6505032d7b0528aa98bc3a66fc1",16481,153),
 "fqhc":("058bd6dbe8dafcb775d1c7eda09fb225197627b4a1a821d3906a65959a63c4ea",875,12),
}

def shape(value):
    if value is None:return "null"
    typ="text" if isinstance(value,str) else "integer" if type(value) is int else "float" if type(value) is float else "other"
    raw=str(value);s=raw.strip()
    if not s:return typ+":blank"
    if len(s)>24:return typ+":over_24"
    p="".join("9" if "0"<=c<="9" else "A" if "A"<=c.upper()<="Z" and len(c.upper())==1 else "S" if c.isspace() else "P" for c in s)
    return typ+":"+p+(":trimmed" if s!=raw else "")

def inspect(path):
    book=openpyxl.load_workbook(path,read_only=True,data_only=True,keep_links=False)
    try:
        require(len(book.worksheets)==1,"unexpected sheet count")
        sheet=book.worksheets[0];sheet.reset_dimensions();rows=iter(sheet.iter_rows(values_only=True))
        m=map_header(next(rows,()))
        require("ccn" in m,"missing key column")
        total=accepted=0;rejected=Counter();types=Counter()
        for ordinal,row in enumerate(rows,2):
            require(ordinal<=MAX_ROWS+1,"row bound")
            if not any(v is not None and v!="" for v in row):continue
            total+=1;value=row[m["ccn"]] if m["ccn"]<len(row) else None
            try:provider_key(value);accepted+=1
            except ValueError:rejected[shape(value)]+=1
        require(total==accepted+sum(rejected.values()),"reconciliation")
        return {"input_rows":total,"accepted_key_rows":accepted,"rejected_key_rows":sum(rejected.values()),
                "rejected_key_shape_counts":dict(rejected),"limits":"No provider values retained; no change to key acceptance or qualification."}
    finally:book.close()

def main():
    p=argparse.ArgumentParser();p.add_argument("--source",choices=PINS,required=True);p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    pin,n,bad=PINS[a.source]
    with tempfile.TemporaryDirectory(prefix="qcor-key-shape-") as d:
        path=Path(d)/"source.xlsx";meta=download(a.source,path)
        require(meta["sha256"]==pin,"source changed; review new release before diagnosis")
        result=inspect(path)
    require(result["input_rows"]==n and result["rejected_key_rows"]==bad,"prior rejection reconciliation")
    result.update({"source":meta,"source_key":a.source,"prior_run":45827150713})
    with a.audit.open("x") as f:json.dump(result,f,indent=2);f.write("\n")
    print("QCOR_KEY_SHAPE_AUDIT",json.dumps(result),flush=True)
if __name__=="__main__":main()
