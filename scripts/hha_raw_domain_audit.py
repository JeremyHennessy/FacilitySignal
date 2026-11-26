"""Aggregate-only HHA raw-domain audit. No source rows or identifiers in receipts."""
import argparse
import csv
from collections import Counter
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
NUMERIC = {"rating", "numerator", "denominator", "reported_percentage", "observed_rate",
           "risk_standardized_rate", "confidence_lower", "confidence_upper",
           "relative_spending", "episode_count"}
COUNTS = {"numerator", "denominator", "episode_count"}
MARKERS = {"": "blank", "-": "dash", "--": "double_dash", "—": "em_dash",
           "not available": "not_available", "n/a": "n/a", "na": "na",
           "not applicable": "not_applicable", "suppressed": "suppressed",
           "not reported": "not_reported", "*": "asterisk", "null": "null_literal"}
OWNERS = {"Non-Profit", "Proprietary", "Government Operated"}
# Unknown raw strings never leave the audit. Preserve distinct states, not guessed meanings.
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)\Z")
DATE = re.compile(r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}\Z")
FOOTNOTE = re.compile(r"(?:[1-9]|1[0-3])(?:[,; ]+(?:[1-9]|1[0-3]))*\Z")

def require(ok, message):
    if not ok:
        raise ValueError(message)

def load():
    lock = json.loads((ROOT / "research/snapshot_release_20261125.json").read_text())
    pin = next(s for s in lock["sources"] if s["key"] == "home-health")
    overlay = json.loads((ROOT / "research/hha_column_semantics_20261126.json").read_text())
    require(pin["sha256"] == overlay["source_sha256"] and pin["release"] == overlay["release"], "source pin mismatch")
    fields = overlay["fields"]
    require(len(fields) == 96 and [f["ordinal"] for f in fields] == list(range(1,97)), "field ordinal mismatch")
    require(sum(f["kind"] in NUMERIC for f in fields) == 60, "numeric scope drift")
    return pin, fields

def check_pin(path, pin):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == pin["bytes"], "source byte count mismatch")
    with path.open("rb") as f:
        require(hashlib.file_digest(f, "sha256").hexdigest() == pin["sha256"], "source hash mismatch")

def fetch(path, pin):
    url = pin["download_url"]
    require(re.fullmatch(r"https://data\.cms\.gov/provider-data/sites/default/files/resources/[A-Za-z0-9_]+/HH_Provider_Oct2026\.csv", url) is not None, "unexpected publisher path")
    require(0 < pin["bytes"] <= 13_000_000, "source size bound")
    n = 0
    with urlopen(url, timeout=45) as response, path.open("xb") as out:
        require(response.geturl() == url, "redirect not admitted")
        while chunk := response.read(1024*1024):
            n += len(chunk)
            require(n <= pin["bytes"], "source exceeded pinned bytes")
            out.write(chunk)
    check_pin(path, pin)

def classify(raw, kind, release):
    v = raw.strip()
    marker = MARKERS.get(v.casefold())
    if marker is not None:
        return marker, None
    if kind == "control_category":
        return ("documented:" + v if v in OWNERS else "unmapped_category"), None
    if kind == "service_indicator":
        return (v.lower() if v.lower() in {"yes", "no"} else "unmapped_category"), None
    if kind == "date":
        if not DATE.fullmatch(v):
            return "date_syntax_review", None
        try:
            d = datetime.strptime(v, "%m/%d/%Y").date()
        except ValueError:
            return "invalid_calendar_date", None
        return ("date_after_release" if d > release else "calendar_date"), None
    if kind == "footnote":
        return ("documented_code_syntax" if FOOTNOTE.fullmatch(v) else "footnote_review"), None
    if kind not in NUMERIC:
        return "nonblank", None
    if len(v) > 64 or not NUMBER.fullmatch(v):
        return "other_nonnumeric", None
    try:
        n = Decimal(v)
    except InvalidOperation:
        return "numeric_syntax_review", None
    if kind in COUNTS:
        ok = n >= 0 and n == n.to_integral_value()
    elif kind == "rating":
        ok = 1 <= n <= 5 and n*2 == (n*2).to_integral_value()
    elif kind == "reported_percentage":
        ok = 0 <= n <= 100
    else:
        # Scale is unresolved. Do not qualify rate or spending ranges by appearance.
        return "numeric_scale_unresolved", n
    return ("numeric_in_candidate_domain" if ok else "numeric_domain_review"), n

def relation(numbers, ordinals, result):
    n, d = (numbers.get(i) for i in ordinals[:2])
    result["both_counts_numeric" if n is not None and d is not None else
           "numerator_only" if n is not None else "denominator_only" if d is not None else "neither_count_numeric"] += 1
    if n is not None and d is not None:
        result["numerator_gt_denominator" if n > d else "numerator_le_denominator"] += 1
        if d == 0:
            result["zero_denominator"] += 1
    if len(ordinals) == 5:
        mid, lo, hi = (numbers.get(i) for i in ordinals[2:])
        if all(v is not None for v in (mid, lo, hi)):
            result["interval_all_numeric"] += 1
            result["interval_ordered" if lo <= mid <= hi else "interval_order_review"] += 1
        else:
            result["interval_incomplete"] += 1

def audit(path, pin, fields):
    check_pin(path, pin)
    release = date.fromisoformat(pin["release"])
    counts = [Counter() for _ in fields]
    mins, maxs = {}, {}
    zero = Counter()
    ownership_other = set()
    pairs = {i: Counter() for i in list(range(18,70,4)) + [70,78,86]}
    rows = 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, strict=True)
        require(next(reader, []) == [x["field"] for x in fields], "exact header mismatch")
        for row in reader:
            rows += 1
            require(rows <= pin["input_rows"] and len(row) == len(fields), "row count/width drift")
            numbers = {}
            for i, (raw, field) in enumerate(zip(row, fields), 1):
                # Contact and identity columns remain presence-only here.
                state, n = classify(raw, field["kind"], release)
                counts[i-1][state] += 1
                if i == 8 and state == "unmapped_category":
                    ownership_other.add(raw.strip())
                    require(len(ownership_other) <= 64, "ownership distinct bound")
                if n is not None:
                    numbers[i] = n
                    mins[i] = min(mins.get(i,n),n)
                    maxs[i] = max(maxs.get(i,n),n)
                    zero[i] += n == 0
            for i, tally in pairs.items():
                relation(numbers, (i,i+1,i+3,i+4,i+5) if i >= 70 else (i,i+1), tally)
    require(rows == pin["input_rows"] == pin["stored_rows"], "source row reconciliation")
    result = []
    for i, (field, tally) in enumerate(zip(fields, counts), 1):
        require(sum(tally.values()) == rows, "field count mismatch")
        entry = {"ordinal":i, "field":field["field"], "kind":field["kind"], "states":dict(tally)}
        if i in mins:
            entry["numeric_min"] = str(mins[i])
            entry["numeric_max"] = str(maxs[i])
            entry["numeric_zero"] = zero[i]
        result.append(entry)
    for p in pairs.values():
        require(sum(p[k] for k in ("both_counts_numeric","numerator_only","denominator_only","neither_count_numeric")) == rows, "paired count mismatch")
        require(p["numerator_gt_denominator"] + p["numerator_le_denominator"] == p["both_counts_numeric"], "paired relation mismatch")
        if p["interval_all_numeric"] or p["interval_incomplete"]:
            require(p["interval_all_numeric"] + p["interval_incomplete"] == rows and p["interval_ordered"] + p["interval_order_review"] == p["interval_all_numeric"], "interval count mismatch")
    check_pin(path, pin)
    return {"status":"AUDIT_COMPLETE_NOT_PUBLICATION_APPROVAL","source_sha256":pin["sha256"],
            "release":pin["release"],"rows":rows,"field_count":len(fields),
            "ownership_unmapped_distinct":len(ownership_other),"fields":result,
            "pair_checks":{str(i):dict(c) for i,c in pairs.items()},
            "new_application_approved_fields":0,"new_public_row_fields":0,
            "limits":"Raw observed domains only. No suppressed values reconstructed; no row-level output; no scale or risk interpretation inferred."}

def main():
    p=argparse.ArgumentParser()
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", type=Path)
    mode.add_argument("--download", action="store_true")
    p.add_argument("--receipt", type=Path, required=True)
    a=p.parse_args()
    require(not a.receipt.exists(),"receipt already exists")
    pin, fields = load()
    with tempfile.TemporaryDirectory(prefix="facilitysignal-hha-domain-") as tmp:
        path=a.source or Path(tmp)/"home-health.csv"
        if a.download:
            fetch(path,pin)
        report=audit(path,pin,fields)
    report["publisher_downloads"]=int(a.download)
    with a.receipt.open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2,sort_keys=True)
    print("HHA_DOMAIN_AUDIT",json.dumps({"rows":report["rows"],"fields":report["field_count"],"rating":report["fields"][15]["states"],"ownership":report["fields"][7]["states"],"ownership_unmapped_distinct":report["ownership_unmapped_distinct"],"date":report["fields"][14]["states"],"pairs":report["pair_checks"]},sort_keys=True))

if __name__ == "__main__":
    main()
