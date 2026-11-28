"""Offline FS-042 score availability audit; no downloads, row output or Azure.
CMS LTCH dictionary v8.0, September 2026, Tables 5-6 and 9 (pp. 9, 12-13, 21-23):
https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/long_term_care_hospital/LTCH_Data_Dictionary.pdf
Only exact single documented footnote tokens are interpreted. Unknown formats
remain unresolved. No clinical units, comparable score or risk is inferred.
"""
import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "research/fs042_ltch_quality_qualification_20261127.json"
MISSING = frozenset({"-", "--", "not available", "not applicable", "n/a", "na", "null"})
FOOTNOTES = {
    "1": "insufficient_sample",
    "2": "period_data_unavailable",
    "3": "shortened_reporting_period",
    "4": "publisher_suppression",
    "5": "not_submitted",
    "6": "lower_confidence_limit_unavailable",
    "7": "not_calculable",
    "8": "waiver_reporting_exemption",
}

def presence(raw):
    token = raw.strip().casefold()
    return "blank" if not token else "missing_literal" if token in MISSING else "present"

def classify(score, footnote, grain):
    if grain not in ("provider", "national"):
        raise ValueError("unknown source grain")
    score_state = presence(score)
    footnote_state = presence(footnote)
    if footnote_state != "present":
        reason = "no_reported_footnote"
    elif grain == "national":
        reason = "unexpected_national_footnote"
    else:
        reason = FOOTNOTES.get(footnote.strip(), "unresolved_footnote")
    # A present score is not necessarily numeric or interpretable; a missing
    # score is never converted to zero, even for footnote 6.
    return score_state, reason

def audit_bytes(data, grain, pin):
    publisher = pin["publisher"]
    if len(data) != publisher["bytes"] or hashlib.sha256(data).hexdigest() != publisher["sha256"]:
        raise ValueError("source bytes do not match qualified release")
    with io.StringIO(data.decode("utf-8-sig"), newline="") as stream:
        reader = csv.reader(stream, strict=True)
        header = next(reader, None)
        if (not header or len(header) != pin["columns"] or
                len(set(header)) != len(header) or set(header) != set(pin["field_presence"])):
            raise ValueError("source schema mismatch")
        score_index, note_index = header.index("Score"), header.index("Footnote")
        notes, scores, joint, note_presence = Counter(), Counter(), Counter(), Counter()
        n = 0
        for row in reader:
            n += 1
            if n > pin["input_rows"] or len(row) != len(header):
                raise ValueError("row count or width drift")
            score, note = row[score_index], row[note_index]
            s, f = classify(score, note, grain)
            scores[s] += 1
            notes[f] += 1
            joint[s + "|" + f] += 1
            note_presence[presence(note)] += 1
        if (n != pin["input_rows"] or dict(scores) != pin["field_presence"]["Score"]
                or dict(note_presence) != pin["field_presence"]["Footnote"] or
                sum(joint.values()) != n or sum(notes.values()) != n):
            raise ValueError("aggregate reconciliation mismatch")
    return {"grain": grain, "input_rows": n, "score_presence": dict(scores),
            "footnote_states": dict(notes), "score_footnote_states": dict(joint),
            "source_sha256": publisher["sha256"], "retained_rows": 0}

def audit_file(path, grain, pin):
    limit = pin["publisher"]["bytes"]
    if not 0 < limit <= 16 * 1024 * 1024:
        raise ValueError("invalid source bound")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    return audit_bytes(data, grain, pin)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", type=Path, required=True)
    parser.add_argument("--national", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    if args.audit.exists():
        raise ValueError("audit exists")
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    pins = receipt["audit"]["sources"]
    result = {"source": "FS-042", "release": "2026-09-23",
              "structural_receipt_run": receipt["run"], "azure_calls": 0,
              "clinical_scores_interpreted": 0, "retained_rows": 0,
              "public_promotion": False,
              "sources": {k: audit_file(getattr(args, k), k, pins[k])
                          for k in ("provider", "national")}}
    with args.audit.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, csv.Error, KeyError) as error:
        # Do not emit input records, identifiers or paths.
        print("FS042_SEMANTIC_AUDIT_FAILED", type(error).__name__)
        raise SystemExit(1) from None
