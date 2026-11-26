"""Assemble the complete, explicitly scoped approved Pages bundle from Blob.

All fifteen archived public packs must match the validated stage receipt and
the approved checkout. Copy only public runtime dependencies; never copy
the whole repository, private databases, archive receipts or credentials.
No deployment or changed-release authorization.
"""
import argparse,hashlib,json,re,shutil
from pathlib import Path
from build_combined import require,sha
from scripts.stage_blob_public_packs import PACKS
ROOT=Path(__file__).resolve().parents[1]
APP_FILES={"index.html","web/pages.js","web/pages.css"}
METADATA_FILES={"research/snapshot_release_20261125.json","research/facilitysignal_source_register_v0.2.json","research/coverage_status.json","research/procurement_awards_audit_20261126.json"}
RUNTIME=PACKS|APP_FILES|METADATA_FILES
def read(p):return json.loads(p.read_text())
def record(path,key):
    require(path.is_file() and not path.is_symlink(),"regular public runtime file required")
    return {"path":key,"bytes":path.stat().st_size,"sha256":sha(path)}
def inventory(root):
    require(root.is_dir() and not root.is_symlink(),"regular stage directory required")
    entries=list(root.rglob("*"))
    require(not any(p.is_symlink() for p in entries),"symlink in public bundle")
    return {p.relative_to(root).as_posix() for p in entries if p.is_file()}
def validate_stage(stage,receipt,root):
    require(receipt["status"]=="PASS" and receipt["public_promotion"] is False and receipt["azure_writes"]==0 and receipt["byte_identical_approved_packs"] is True and receipt["market_rebuilt"] is True and receipt["existing_enrichment_pins_preserved"] is True,"approved Blob stage gate")
    pins={r["path"]:r for r in receipt["files"]}
    require(len(receipt["files"])==len(pins)==receipt["pack_count"]==15 and set(pins)==PACKS and inventory(stage)==PACKS,"exact public pack scope")
    require(receipt["bytes"]==sum(p["bytes"] for p in pins.values()),"public pack byte count")
    for key,pin in pins.items():
        require(type(pin["bytes"]) is int and pin["bytes"]>0 and re.fullmatch(r"[a-f0-9]{64}",pin["sha256"]),"public pack pin")
        want={k:pin[k] for k in ("path","bytes","sha256")}
        require(record(stage/key,key)==record(root/key,key)==want,"staged pack or approved checkout differs: "+key)
    return pins
def build(stage,stage_receipt,out,manifest,root=ROOT):
    require(not out.exists() and not manifest.exists(),"new bundle output required")
    receipt=read(stage_receipt);validate_stage(stage,receipt,root)
    runtime=set(RUNTIME)
    supplement={"web/institutional-evidence.json","web/institutional-evidence-manifest.json"}
    present={key for key in supplement if (root/key).exists()}
    if present:
        require(present==supplement,"incomplete institutional public candidate bundle")
        from scripts.stage_institutional_public_candidate import manifest_for
        require(root.resolve()==ROOT.resolve(),"institutional candidate requires exact repository inputs")
        require(read(root/"web/institutional-evidence-manifest.json")==manifest_for(root/"web"),"institutional candidate qualification drift")
        runtime.update(supplement)
    out.mkdir(parents=True)
    records=[]
    for key in sorted(runtime):
        source=(stage if key in PACKS else root)/key
        pin=record(source,key);dest=out/key;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest);require(record(dest,key)==pin,"public bundle copy mismatch")
        records.append(pin)
    require(inventory(out)==runtime,"bundle file scope")
    html=(out/"index.html").read_text()
    for key in ("web/pages.js","web/pages.css"):
        require(key+"?v="+sha(out/key)[:16] in html,"approved versioned runtime asset mismatch")
    # Cross-check runtime metadata before running the real browser.
    lock=read(out/"research/snapshot_release_20261125.json")
    register=read(out/"research/facilitysignal_source_register_v0.2.json")
    coverage=read(out/"research/coverage_status.json")
    require(isinstance(lock["sources"],list) and isinstance(register["sources"],list) and isinstance(coverage["sources"],list),"runtime metadata scope")
    require(len({s["key"] for s in lock["sources"] if s["family"]=="care-compare"})==9,"runtime Care Compare source scope")
    result={"status":"APPROVED_BASELINE_BUNDLE_STAGED","base_release":receipt["base_release"],"blob_data_pack_count":len(PACKS),"runtime_file_count":len(records),"bundle_bytes":sum(x["bytes"] for x in records),"files":records,"stage_receipt_sha256":sha(stage_receipt),"historical_baseline_unchanged":True,"public_promotion":False,"azure_writes":0,"changed_release_authorization":False,"required_before_new_public_release":["new publisher release observed and privately qualified","complete versioned source and evidence lineage","all dependent packs and historical public intelligence reviewed","candidate browser assertions and actual screenshot review","owner-approved exact release checkpoint and rollback plan"]}
    with manifest.open("x",encoding="utf-8") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print("FACILITYSIGNAL_PAGES_BUNDLE_STAGED",json.dumps({k:v for k,v in result.items() if k!="files"},sort_keys=True),flush=True)
    return result
def main():
    p=argparse.ArgumentParser();p.add_argument("--stage",type=Path,required=True);p.add_argument("--stage-receipt",type=Path,required=True);p.add_argument("--out",type=Path,required=True);p.add_argument("--manifest",type=Path,required=True);a=p.parse_args()
    build(a.stage,a.stage_receipt,a.out,a.manifest)
if __name__=="__main__":main()
