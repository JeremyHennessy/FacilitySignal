"""FS-043 IRF quality reporting: one pinned CMS provider release, aggregate only.

Source-native CCN/measure/window observations. No clinical scores, facility
identifiers, contact data, or row-level files leave temporary storage.
"""
import argparse
import csv
import hashlib
import json
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import collect_cms as cms
from build_combined import require, sha
from local_research import STATES

RELEASE = "2026-09-23"
MAX_BYTES = 32 * 1024 * 1024
CCN = "CMS Certification Number (CCN)"
TAIL = ["Measure Code", "Score", "Footnote", "Start Date", "End Date", "Measure Date Range"]
SPECS = {
    "provider": ("v9e4-nwhh", "2026-09-11", 79430,
                 [CCN, "Provider Name", "Address Line 1", "Address Line 2", "City/Town",
                  "State", "ZIP Code", "County/Parish", "Telephone Number", "CMS Region"] + TAIL),
}
MISSING = {"-", "--", "not available", "not applicable", "n/a", "na", "null"}

def presence(raw):
    v = raw.strip()
    return "blank" if not v else "missing_literal" if v.casefold() in MISSING else "present"

def date(raw):
    try:
        return datetime.strptime(raw.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None

def screen(stream, kind, expected):
    require(kind in SPECS and type(expected) is int and 0 < expected <= 80000, "source bound")
    header = SPECS[kind][3]
    reader = csv.reader(stream, strict=True)
    require(next(reader, None) == header, "IRF header drift")
    profiles = [Counter() for _ in header]
    keys, ids, codes = set(), set(), set()
    windows, geography, shapes = Counter(), Counter(), Counter()
    repeated = unresolved = n = 0
    for n, row in enumerate(reader, 1):
        require(n <= expected and len(row) == len(header), "IRF width/count drift")
        for value, profile in zip(row, profiles):
            profile[presence(value)] += 1
        v = dict(zip(header, (x.strip() for x in row)))
        ident, code = v[CCN], v["Measure Code"]
        valid_id = bool(re.fullmatch(r"[0-9]{6}", ident))
        shapes["expected" if valid_id else "unresolved"] += 1
        if kind == "provider":
            state = v["State"]
            geography[state if state in STATES else "unknown_or_other"] += 1
        if valid_id:
            ids.add(ident)
        valid_code = bool(re.fullmatch(r"[A-Z0-9_]{1,100}", code))
        if valid_code:
            codes.add(code)
        start, end = date(v["Start Date"]), date(v["End Date"])
        if start is not None and end is not None and start <= end:
            windows["ordered_explicit_dates"] += 1
        elif presence(v["Start Date"]) != "present" and presence(v["End Date"]) != "present":
            windows["missing_dates"] += 1
        else:
            windows["unresolved_dates"] += 1
        # Raw publisher window tokens preserve unresolved periods; no date imputation.
        if not valid_id or not valid_code:
            unresolved += 1
        else:
            key = (ident, code, v["Start Date"], v["End Date"], v["Measure Date Range"])
            if key in keys:
                repeated += 1
            keys.add(key)
    require(n == expected == len(keys)+repeated+unresolved, "IRF row reconciliation")
    require(all(sum(p.values()) == n for p in profiles) and sum(windows.values()) == n
            and sum(shapes.values()) == n and sum(geography.values()) == n,
            "IRF aggregate reconciliation")
    return {"input_rows":n,"columns":len(header),
            "field_presence":dict(zip(header,map(dict,profiles))),
            "distinct_expected_identifier_tokens":len(ids),"distinct_measure_code_tokens":len(codes),
            "provisional_distinct_keys":len(keys),"repeated_key_rows":repeated,
            "unresolved_key_rows":unresolved,"identifier_shapes":dict(shapes),
            "date_window_states":dict(windows),
            "jurisdiction_row_counts":dict(geography),"jurisdictions":len(set(geography)&STATES)}

def acquire(kind, root):
    ident, modified, expected, _ = SPECS[kind]
    meta = cms.metadata(ident)
    require(meta["released"] == RELEASE and meta["modified"] == modified
            and cms.count(ident) == expected, "IRF release/count drift")
    path = root / (kind + ".csv")
    size = 0
    digest = hashlib.sha256()
    with cms.response(meta["url"]) as response, path.open("xb") as out:
        cms.allowed(response.geturl())
        while chunk := response.read(1024*1024):
            size += len(chunk)
            require(size <= MAX_BYTES, "IRF byte bound")
            digest.update(chunk)
            out.write(chunk)
    require(size > 0 and sha(path) == digest.hexdigest(), "IRF source integrity")
    require(cms.metadata(ident) == meta and cms.count(ident) == expected, "IRF publisher drift")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        result = screen(stream, kind, expected)
    require(sha(path) == digest.hexdigest(), "IRF input changed")
    return {**result,"publisher":{**meta,"bytes":size,"sha256":digest.hexdigest()}}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit",type=Path,required=True)
    args = p.parse_args()
    require(not args.audit.exists(), "audit exists")
    with tempfile.TemporaryDirectory(prefix="fs043-private-") as tmp:
        sources = {k:acquire(k, Path(tmp)) for k in SPECS}
    result = {"source_id":"FS-043","sources":sources,
              "retrieved_at":datetime.now(timezone.utc).isoformat(),
              "input_rows":sum(x["input_rows"] for x in sources.values()),
              "row_level_retained":0,"azure_writes":0,"canonical_matches":0,
              "reuse_review":"pending","public_promotion":False,
              "scope":"Historical quality reporting structural qualification only. IRF provider observations only; other FS-043 datasets remain unqualified. Measure values, footnotes and units not interpreted; no facility risk, current certification, physical property or service failure inferred."}
    with args.audit.open("x",encoding="utf-8") as out:
        json.dump(result,out,indent=2,sort_keys=True)
        out.write("\n")
    print("FS043_AGGREGATE_AUDIT",json.dumps(result,sort_keys=True),flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("FS043_QUALIFICATION_FAILED",type(error).__name__,flush=True)
        raise SystemExit(1) from None
