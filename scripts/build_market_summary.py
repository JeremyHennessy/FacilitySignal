"""Precompute public provider market counts without retrieving or publishing new source records."""
import argparse,hashlib,json
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/"web/public-directory"
OUT=ROOT/"web/market-summary.json"
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(path.read_bytes())
def require(test,msg):
    if not test:raise ValueError(msg)
def build(root=ROOT):
    directory=root/"web/public-directory"
    manifest=read(directory/"manifest.json")
    lock=read(root/"research/snapshot_release_20261125.json")
    # The lock names each approved public source and exact release.
    by_key={s["key"]:s for s in lock["sources"] if s["family"]=="care-compare" and not s["key"].startswith("nursing-")}
    keys=sorted(by_key)
    require(len(keys)==7,"Expected seven provider sources")
    states=sorted(manifest["jurisdictions"])
    require(len(states)==len(set(states))==56,"Jurisdiction manifest invalid")
    regions={state:{key:0 for key in keys} for state in states}
    sources={}
    for key in keys:
        raw=(directory/(key+".json")).read_bytes()
        d=json.loads(raw);rows=d["records"];release=by_key[key]["release"]
        expected=manifest["sources"][key]["source_rows"]
        require(d["source"]==key and d["release"]==release and d["row_count"]==len(rows)==expected==manifest["sources"][key]["published_records"]==by_key[key]["stored_rows"],"Source mismatch "+key)
        counts=Counter(row["state"] for row in rows)
        require(set(counts)<=set(states),"Unrecognized jurisdiction "+key)
        for state in states:regions[state][key]=counts[state]
        sources[key]={"release":release,"rows":expected,"sha256":sha(raw)}
    total=sum(x["rows"] for x in sources.values())
    require(total==manifest["provider_rows"]==sum(sum(row.values()) for row in regions.values()),"National reconciliation")
    return {"version":1,"scope":"precomputed public provider source record counts only","as_of":manifest["as_of"],"source_database_sha256":manifest["source_database_sha256"],"public_manifest_sha256":sha((directory/"manifest.json").read_bytes()),"provider_rows":total,"sources":sources,"regions":regions}
def main():
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--write",action="store_true");g.add_argument("--check",action="store_true")
    a=p.parse_args();data=build()
    if a.write:OUT.write_text(json.dumps(data,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
    elif read(OUT)!=data:raise SystemExit("Regional market summary is stale")
    print("PUBLIC_MARKET_SUMMARY_PASS",json.dumps({"regions":len(data["regions"]),"source_rows":data["provider_rows"],"bytes":OUT.stat().st_size,"provider_shard_bytes":sum((DIR/(k+".json")).stat().st_size for k in data["sources"]),"sha256":sha(OUT.read_bytes())}),flush=True)
if __name__=="__main__":main()
