"""Generate only the explicitly specified public aggregate evidence projection."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def read(path):
    return json.loads(path.read_text(encoding="utf-8"))
def build(ledger,cap,spec):
    epa=next(x for x in ledger["sources"] if x["id"]=="FS-157")
    ctx={"ledger":ledger,"cap":cap,"epa":epa}
    def resolve(cell):
        if isinstance(cell,dict):
            if set(cell)!={"path"}:raise ValueError("unexpected field selector")
            val=ctx
            for key in cell["path"]:val=val[key]
        else:val=cell
        if val is None or type(val) is int and val>=0 or isinstance(val,str) and len(val)<=300:return val
        raise ValueError("unexpected public cell type")
    result=[]
    for section in spec["sections"]:
        groups=[]
        for g in section["groups"]:
            groups.append({**{k:g[k] for k in ("id","title","note","run","columns","source")},"rows":[[resolve(c) for c in row] for row in g["rows"]]})
            if any(len(row)!=len(g["columns"]) for row in groups[-1]["rows"]):raise ValueError("table width")
        result.append({**{k:section[k] for k in ("id","title","intro")},"groups":groups})
    return {"version":1,"scope":"historical national aggregate qualification","sections":result}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--check",action="store_true")
    a=p.parse_args()
    obj=build(read(ROOT/"research/coverage_status.json"),read(ROOT/"research/public_capability_audit_20261126.json"),read(ROOT/"scripts/public_intelligence_spec.json"))
    out=ROOT/"web/public-intelligence.json"
    if a.check:
        if read(out)!=obj:raise SystemExit("Public intelligence projection differs from selected qualification evidence")
    else:out.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
if __name__=="__main__":main()
