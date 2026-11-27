"""Qualify national CMS HAI benchmark context without calculating provider risk."""
import csv
from collections import Counter
from datetime import datetime
from decimal import Decimal
import io
import re

FIELDS=("Measure ID","Measure Name","Score","Footnote","Start Date","End Date")
GROUPS={f"HAI_{i}_SIR" for i in range(1,7)}
RELEASE_DATE=datetime(2026,11,12).date()

def period(start,end):
    if not all(isinstance(x,str) and re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}",x)
               for x in (start,end)):
        raise ValueError("Unexpected calendar shape")
    dates=[datetime.strptime(x,"%m/%d/%Y").date() for x in (start,end)]
    if not dates[0]<=dates[1]<=RELEASE_DATE:
        raise ValueError("Invalid publication boundary")
    return tuple(x.isoformat() for x in dates)

def score(raw):
    if raw=="Not Available" or raw=="":
        return None
    if not isinstance(raw,str) or len(raw)>24 or not re.fullmatch("[0-9]+(?:[.][0-9]+)?",raw):
        raise ValueError("Unexpected score domain")
    return Decimal(raw)

def benchmark(rows):
    if len(rows)!=6 or {r["Measure ID"] for r in rows}!=GROUPS:
        raise ValueError("Expected each of six national SIR benchmarks exactly once")
    lookup={}
    for r in rows:
        if set(r)!=set(FIELDS) or not r["Measure Name"] or r["Footnote"] or score(r["Score"])!=1:
            raise ValueError("Unexpected benchmark schema, annotation or reference value")
        dates=period(r["Start Date"],r["End Date"])
        lookup[r["Measure ID"],*dates]=True
    return lookup

def from_csv(raw):
    if not isinstance(raw,bytes) or not 1<=len(raw)<=32768:
        raise ValueError("CSV byte cap")
    reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig"),newline=""),strict=True)
    if tuple(reader.fieldnames or [])!=FIELDS:
        raise ValueError("CSV header changed")
    rows=[]
    for row in reader:
        if None in row or None in row.values() or len(rows)>=6:
            raise ValueError("CSV row count or shape changed")
        rows.append(row)
    return benchmark(rows)

def summarize(provider_rows, lookup):
    counts=Counter()
    labels=Counter()
    for r in provider_rows:
        group=r["Measure ID"]
        if group not in GROUPS:
            counts["other_metric_not_used_for_benchmark"]+=1
            continue
        start,end=period(r["Start Date"],r["End Date"])
        value=score(r["Score"])
        if (group,start,end) not in lookup:
            counts["no_exact_period_benchmark"]+=1
        elif value is None:
            counts["source_score_unavailable"]+=1
            counts["unavailable_with_footnote"]+=bool(r["Footnote"])
        else:
            counts["numeric_sir_exact_benchmark_context"]+=1
            labels[r["Compared to National"] if r["Compared to National"] in {
                "Better than the National Benchmark","No Different than National Benchmark",
                "Worse than the National Benchmark"} else "unqualified_label"]+=1
    return {"provider_screen_rows":len(provider_rows),"row_dispositions":dict(counts),
            "publisher_labels_on_numeric_members":dict(labels),"facility_rows_emitted":0,
            "physical_site_attributions":0,"risk_scores_calculated":0}
