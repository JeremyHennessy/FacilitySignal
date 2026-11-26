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
    pecos_path=ROOT/"research/pecos_role_semantic_audit_20261126.json"
    followup_path=ROOT/"research/pecos_semantic_followup_20261126.json"
    if pecos_path.exists() and followup_path.exists():
        pecos=read(pecos_path);follow=read(followup_path)
        pins={s["key"]:s for s in read(ROOT/"research/snapshot_release_20261125.json")["sources"]}
        if pecos["qualification_run"]!=45828076053 or follow["qualification_run"]!=45828422101:
            raise ValueError("Unqualified PECOS evidence")
        if set(pecos["sources"])!={f+"-"+s for f in ("hospital","snf") for s in ("enrollment","owner","chow")}:
            raise ValueError("Unexpected PECOS source set")
        for k,s in pecos["sources"].items():
            if any(s[f]!=pins[k][f] for f in ("sha256","stored_rows","input_rows","excluded_rows","release")):
                raise ValueError("PECOS release mismatch")
        for k,h in follow["source_hashes"].items():
            if pins[k]["sha256"]!=h:raise ValueError("Follow-up release mismatch")
        for fam,v in pecos["families"].items():
            own=v["owner"];n=own["counts"]["organizational_rows"]
            if n!=pins[fam+"-owner"]["stored_rows"] or own["role_text_agreement"]!={"matches":n} or sum(own["role_class_counts"].values())!=n:
                raise ValueError("Role reconciliation failed")
            if any(sum(x["rows"].values())!=n for x in own["flags"].values()):
                raise ValueError("Flag reconciliation failed")
            for c in ("direct_ownership","indirect_ownership","management","financial_interest","partnership","other","additional_disclosable_party","trustee"):
                if c not in own["role_class_counts"]:own["role_class_counts"][c]=None
            for c in ("AM","CH","CO"):
                v["chow"]["code_counts"].setdefault(c,0)
            label=follow["result"][fam+"-chow"]["counts"]
            if sum(label.get(k,0) for k in ("current_dictionary","documented_earlier_dictionary_variant"))!=pins[fam+"-chow"]["stored_rows"]:
                raise ValueError("CHOW wording not reconciled")
        subgroup=follow["result"]["hospital-enrollment"]
        if subgroup["rows"]!=pins["hospital-enrollment"]["stored_rows"] or any(sum(x.values())!=subgroup["rows"] or set(x)-{"yes","no"} for x in subgroup["subgroup_flag_counts"].values()):
            raise ValueError("Subgroup reconciliation failed")
        ctx["pecos_semantic"]=pecos
        ctx["pecos_followup"]=follow["result"]
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
