"""Generate only the explicitly specified public aggregate evidence projection."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def read(path):
    return json.loads(path.read_text(encoding="utf-8"))
def build(ledger,cap,spec,data_use=None):
    epa=next(x for x in ledger["sources"] if x["id"]=="FS-157")
    ctx={"ledger":ledger,"cap":cap,"epa":epa}
    if data_use is None:
        path=ROOT/"research/qualified_data_use_20261126.json"
        if path.exists():data_use=read(path)
    if data_use is not None:ctx["data_use"]=data_use
    clia_path=ROOT/"research/clia_domain_link_audit_20261126.json"
    if clia_path.exists():ctx["clia_audit"]=read(clia_path)
    nursing_path=ROOT/"research/nursing_semantic_audit_20261126.json"
    if nursing_path.exists():
        nursing=read(nursing_path)
        groups={a["group"]:a["result"] for a in nursing["audits"]}
        if set(groups)!={"chains","citations"} or nursing["qualification_run"]!=45826186143:
            raise ValueError("Unexpected nursing semantic audit")
        for name,s in groups["citations"].items():
            if any(sum(c.values())!=s["rows"] or set(c)-{"yes","no"} for c in s["flags"].values()):
                raise ValueError("Nursing flag domain or count mismatch")
            s["flag_yes"]={f:c.get("yes",0) for f,c in s["flags"].items()}
        ctx["nursing_semantic"]=groups
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
