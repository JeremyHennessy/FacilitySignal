"""Offline aggregate audit: same-CCN/date penalty and survey observations, never an event join."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sqlite3

EXT_SHA256 = "4090f140a45bdee990a0669e357d6d8d4672aff829ff0e52fb8f34e2e5d7e9bf"
CUTOFF = date(2026, 10, 28)
ROW_PINS = {"penalty": 15007, "inspection_dates": 148956, "survey_summary": 43931}
SURVEYS = {"inspection_dates": ("ccn_present", ("date1",)),
           "survey_summary": ("same_state", ("date1", "date2"))}
KINDS = ("Fine", "Payment Denial")
RESULT_BUCKETS = ("unresolved_directory", "missing_penalty_date", "invalid_penalty_date",
                  "penalty_date_after_release", "neither_survey_source",
                  "only_ccn_only_inspection_dates", "only_prior_same_state_summary",
                  "both_survey_sources")

def day(raw):
    if raw is None or raw == "":
        return "missing", None
    if not isinstance(raw, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw) is None:
        return "invalid", None
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        return "invalid", None
    return ("after_release", None) if d > CUTOFF else ("in_window", d.isoformat())

def concordance(db):
    """Read a previously qualified connection; report no provider identifiers or source dates."""
    sets = {}
    survey_coverage = {}
    for table, (eligible_state, cols) in SURVEYS.items():
        keys = set()
        counts = Counter()
        for ccn, linkage, *dates in db.execute("SELECT ccn,link_state," + ",".join(cols) + " FROM " + table):
            counts["source_rows"] += 1
            if linkage != eligible_state:
                counts["unresolved_directory_rows"] += 1
                continue
            counts["directory_candidate_rows"] += 1
            for col, raw in zip(cols, dates):
                state, normalized = day(raw)
                counts[col+"_"+state] += 1
                if normalized is not None:
                    keys.add((ccn, normalized))
        sets[table] = keys
        survey_coverage[table] = {**counts, "distinct_directory_candidate_ccn_dates": len(keys)}

    counts = {kind: Counter(dict.fromkeys(RESULT_BUCKETS, 0)) for kind in KINDS}
    for ccn, linkage, pd, kind in db.execute("SELECT ccn,link_state,penalty_date,kind FROM penalty"):
        if kind not in KINDS:
            raise ValueError("Unexpected penalty kind")
        state, normalized = day(pd)
        if linkage != "same_state":
            bucket = "unresolved_directory"
        elif state != "in_window":
            bucket = {"missing":"missing_penalty_date", "invalid":"invalid_penalty_date",
                      "after_release":"penalty_date_after_release"}[state]
        else:
            key = (ccn, normalized)
            inspection = key in sets["inspection_dates"]
            summary = key in sets["survey_summary"]
            bucket = ("both_survey_sources" if inspection and summary else
                      "only_ccn_only_inspection_dates" if inspection else
                      "only_prior_same_state_summary" if summary else "neither_survey_source")
        counts[kind][bucket] += 1
    return {"scope":"Historical source-row concordance at exact CCN/date only. Inspection dates are CCN-only candidates; summary retains prior same-state flag, not raw state. Date overlap does not prove same inspection, causal connection, case identity, payment, open enforcement or compliance.",
            "release_cutoff":CUTOFF.isoformat(), "survey_field_coverage":survey_coverage,
            "penalty_source_rows_by_kind":{kind:sum(c.values()) for kind,c in counts.items()},
            "penalty_source_rows_by_kind_and_date_concordance":counts,
            "canonical_event_links":0, "provider_rows_emitted":0}

def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def profile(path):
    if not path.is_file() or path.is_symlink() or sha(path) != EXT_SHA256:
        raise ValueError("Expected exact regular local extension database")
    with closing(sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
        for name,count in ROW_PINS.items():
            if db.execute("SELECT count(*) FROM "+name).fetchone()[0] != count:
                raise ValueError("Pinned source count mismatch")
        result = concordance(db)
    if sha(path) != EXT_SHA256:
        raise ValueError("Extension database changed during audit")
    result["extension_sha256"] = EXT_SHA256
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extension",type=Path,required=True)
    print(json.dumps(profile(parser.parse_args().extension),sort_keys=True))
