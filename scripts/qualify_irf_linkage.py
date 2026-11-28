"""FS-043 pinned IRF provider/directory identity audit. Aggregate output only."""
import argparse
import csv
import io
import json
import re
from collections import Counter
from pathlib import Path
from scripts import qualify_irf_provider as prior
from scripts.qualify_ltch_provider_linkage import (classify, require, read_local, retrieve)

ROOT = Path(__file__).resolve().parents[1]
CCN = prior.CCN
PROVIDER = prior.SPECS["provider"][3]
DIRECTORY = PROVIDER[:10] + ["Ownership Type", "Certification Date"]
CONTEXT = ("State", "Provider Name", "Address Line 1", "City/Town", "ZIP Code")

def shape(token):
    if re.fullmatch(r"[0-9]{6}", token):
        return "numeric_rehab_range" if 3025 <= int(token[2:]) <= 3099 else "numeric_other_range"
    if re.fullmatch(r"[0-9]{2}[RT][0-9]{3}", token):
        return "unit_" + token[2]
    if re.fullmatch(r"[0-9]{2}T[ABCEFGHJK][0-9]{2,3}", token):
        return "extended_documented_marker_candidate"
    return "unresolved"

def records(payload, header, count):
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline=""), strict=True)
    require(reader.fieldnames == header, "IRF linkage header drift")
    n = 0
    for n, row in enumerate(reader, 1):
        require(n <= count and None not in row and None not in row.values(), "IRF width/count drift")
        yield row
    require(n == count, "IRF linkage count drift")

def screen(directory_bytes, provider_bytes, directory_count, provider_count):
    directory = {}
    for row in records(directory_bytes, DIRECTORY, directory_count):
        token = row[CCN]
        require(token and token not in directory, "missing or duplicate directory token")
        directory[token] = {k:row[k] for k in CONTEXT}
    keys, by_token = set(), {}
    row_shapes, row_links, token_shapes, dir_shapes = Counter(), Counter(), Counter(), Counter()
    for token in directory:
        dir_shapes[shape(token)] += 1
    for row in records(provider_bytes, PROVIDER, provider_count):
        token = row[CCN]
        key = tuple(row[k] for k in (CCN, "Measure Code", "Start Date", "End Date", "Measure Date Range"))
        require(token and row["Measure Code"] and key not in keys, "missing or duplicate reporting key")
        keys.add(key)
        kind = shape(token)
        status = classify(directory.get(token), row)
        row_shapes[kind] += 1
        row_links[status] += 1
        by_token.setdefault(token, set()).add(status)
    token_links = Counter()
    for token, states in by_token.items():
        token_shapes[shape(token)] += 1
        token_links[next(iter(states)) if len(states)==1 else "mixed_evidence"] += 1
    require(len(keys) == provider_count == sum(row_shapes.values()) == sum(row_links.values()), "row reconciliation")
    require(len(by_token) == sum(token_shapes.values()) == sum(token_links.values()), "token reconciliation")
    intersection = set(directory) & set(by_token)
    return {"provider_rows":provider_count,"directory_rows":directory_count,
            "provider_tokens":len(by_token),"distinct_reporting_keys":len(keys),
            "exact_token_intersection":len(intersection),
            "directory_only":len(set(directory)-set(by_token)),
            "provider_only":len(set(by_token)-set(directory)),
            "provider_row_shapes":dict(row_shapes),"provider_token_shapes":dict(token_shapes),
            "directory_token_shapes":dict(dir_shapes),
            "observation_link_states":dict(row_links),"provider_link_states":dict(token_links),
            "canonical_matches":0,"parent_matches":0,"retained_rows":0,"azure_calls":0,
            "boundary":"Exact source-native identifier and same-release text context only. No inferred parent CCN, physical property, current operation or clinical score interpretation."}

def pins():
    d = next(x for x in json.loads((ROOT/"research/snapshot_release_20261125.json").read_text())["sources"] if x["key"]=="rehabilitation")
    q = json.loads((ROOT/"research/fs043_irf_provider_qualification_20261128.json").read_text())["audit"]["sources"]["provider"]
    p = q["publisher"]
    require(d["catalog_id"]=="7t8x-u3ir" and d["release"]==p["released"]==prior.RELEASE
            and d["input_rows"]==1222 and p["id"]=="v9e4-nwhh" and q["input_rows"]==79430
            and d["bytes"]==159829 and p["bytes"]==12935784, "IRF source pin drift")
    return {"directory":{"id":d["catalog_id"],"modified":"2026-08-12","rows":d["input_rows"],
                          "bytes":d["bytes"],"sha256":d["sha256"],"url":d["download_url"]},
            "provider":{"id":p["id"],"modified":p["modified"],"rows":q["input_rows"],
                         "bytes":p["bytes"],"sha256":p["sha256"],"url":p["url"]}}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path)
    p.add_argument("--provider", type=Path)
    p.add_argument("--retrieve-pinned-public", action="store_true")
    p.add_argument("--audit", required=True, type=Path)
    a = p.parse_args()
    require(not a.audit.exists(), "audit exists")
    require((a.retrieve_pinned_public and not a.directory and not a.provider) or
            (not a.retrieve_pinned_public and a.directory and a.provider), "choose one input mode")
    pin = pins()
    d = retrieve(pin["directory"]) if a.retrieve_pinned_public else read_local(a.directory,pin["directory"])
    q = retrieve(pin["provider"]) if a.retrieve_pinned_public else read_local(a.provider,pin["provider"])
    result = screen(d,q,pin["directory"]["rows"],pin["provider"]["rows"])
    result.update({"source_id":"FS-043","release":prior.RELEASE,"pins":pin,
                   "input_mode":"publisher" if a.retrieve_pinned_public else "verified_local",
                   "identifier_reference":"https://www.cdc.gov/nhsn/PDFs/irf/Updating-IRF-locations-within-NHSN.pdf",
                   "public_row_clearance":"pending"})
    with a.audit.open("x",encoding="utf-8") as out:
        json.dump(result,out,indent=2,sort_keys=True)
        out.write("\n")
    print("FS043_LINKAGE_AGGREGATE",json.dumps(result,sort_keys=True),flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("FS043_LINKAGE_FAILED",type(error).__name__,flush=True)
        raise SystemExit(1) from None
