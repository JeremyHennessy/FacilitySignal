"""Aggregate validation of the rendered CMS hospital-price-enforcement portal table.

Input: only the line-numbered text from the official portal as rendered by a text reader.
No network, provider/notice row output, or claim about unlisted cases.
"""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import re

PORTAL = "https://www.cms.gov/priorities/key-initiatives/hospital-price-transparency/enforcement-actions"
MAX_BYTES = 262144
MAX_ROWS = 200
DATE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
LINK = re.compile(r"【([0-9]+)†("+DATE+r") \(PDF\)】")
HEADER = ("Date Action Taken", "Hospital Name", "Effective Date")

def qualify(raw):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError("Invalid portal extract size")
    all_lines = [(int(n), text.strip()) for line in raw.decode("utf-8").splitlines()
                 if (match := re.fullmatch(r"L([0-9]+): ?(.*)", line))
                 for n, text in [match.groups()]]
    anchors = [i for i, (_, line) in enumerate(all_lines)
               if tuple(col.strip() for col in line.split("|")) == HEADER]
    if len(anchors) != 1:
        raise ValueError("Expected one matching table")
    start = anchors[0]
    expected = all_lines[start][0]
    active = False
    counts = Counter()
    notices_by_year = Counter()
    effective_year = Counter()
    review_states = Counter()
    document_multiplicity = Counter()
    chronology = Counter()
    ids = set()
    min_doc = max_doc = min_eff = max_eff = None
    for number, line in all_lines[start:]:
        if number != expected:
            raise ValueError("Rendered lines truncated or reordered")
        expected += 1
        if not active:
            if number == all_lines[start][0]:
                continue
            if tuple(col.strip() for col in line.split("|")) != ("---",)*3:
                raise ValueError("Rendered table separator changed")
            active = True
            continue
        if not line:
            break
        if counts["portal_rows"] >= MAX_ROWS:
            raise ValueError("Portal row cap")
        cols = tuple(col.strip() for col in line.split("|"))
        if len(cols) != 3 or not cols[1] or not re.fullmatch(DATE, cols[2]):
            raise ValueError("Unexpected portal row shape")
        links = LINK.findall(cols[0])
        if not links or LINK.sub("",cols[0]).strip():
            raise ValueError("Unexpected notice links")
        effective = date.fromisoformat(cols[2])
        min_eff = effective if min_eff is None else min(min_eff,effective)
        max_eff = effective if max_eff is None else max(max_eff,effective)
        effective_year[effective.year] += 1
        for key, display_date in links:
            if key in ids:
                raise ValueError("Repeated rendered document reference")
            ids.add(key)
            dt = date.fromisoformat(display_date)
            min_doc = dt if min_doc is None else min(min_doc,dt)
            max_doc = dt if max_doc is None else max(max_doc,dt)
            notices_by_year[dt.year] += 1
            chronology["effective_eq_notice" if effective==dt else
                       "effective_before_notice" if effective<dt else "effective_after_notice"] += 1
        review_states["under_review_label" if re.search(r"\bUnder Review\s*\*",cols[1],re.I) else "no_under_review_label"] += 1
        document_multiplicity["single_document_row" if len(links)==1 else "multi_document_row"] += 1
        counts["portal_rows"] += 1
    else:
        raise ValueError("Portal extract lacks table terminator")
    if not counts["portal_rows"]:
        raise ValueError("Empty portal table")
    return {"source":PORTAL,"status":"official_rendered_table_aggregate_verified",
            "sha256_scope":"exact input rendered text extract, not raw publisher HTML",
            "rendered_extract_sha256":hashlib.sha256(raw).hexdigest(),"portal_rows":counts["portal_rows"],
            "rendered_notice_links":len(ids),"notice_year_link_counts":dict(notices_by_year),
            "effective_year_row_counts":dict(effective_year),"review_label_row_counts":dict(review_states),
            "notice_links_per_row":dict(document_multiplicity),"date_order_per_link":dict(chronology),
            "notice_date_range":[str(min_doc),str(max_doc)],"effective_date_range":[str(min_eff),str(max_eff)],
            "canonical_events":0,"provider_identity_links":0,"row_output":False,
            "limitations":"Snapshot of the displayed notices only; not all compliance activity, historical cases, current compliance, adjudications, liabilities, equipment, or a provider-level feed. A missing review label does not establish finality."}

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input",type=Path)
    args=parser.parse_args()
    with args.input.open("rb") as f:
        print(json.dumps(qualify(f.read(MAX_BYTES+1)),indent=2,sort_keys=True))
