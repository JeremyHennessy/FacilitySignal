"""Audits an official rendered, bounded Rural Emergency Hospital OP-36 display."""
from collections import Counter
from decimal import Decimal
import re

PERIOD=("01/01/2024","12/31/2024")
RELEASE="2026-11-12"
MEASURE="REH_OP_36"
MISSING="Not Available"
FLAGS={"1":"too_few_to_report","5":"unavailable_reason_unspecified","7":"no_eligible_cases"}

def number(raw):
    if not isinstance(raw,str) or not re.fullmatch(r"[0-9]+(?:[.][0-9]+)?",raw):
        raise ValueError("Non-finite or unknown number")
    return Decimal(raw)

def count(raw):
    if not isinstance(raw,str) or not re.fullmatch(r"[0-9]+",raw):
        raise ValueError("Noninteger count")
    return int(raw)

def qualify(national,providers,*,release):
    if release!=RELEASE or len(national)!=1 or not 1<=len(providers)<=49:
        raise ValueError("Wrong pinned edition or preview bounds")
    measure,rate,worse,same,better,too_few,flag,*window=national[0]
    if measure!=MEASURE or tuple(window)!=PERIOD or rate!=MISSING or flag!="5":
        raise ValueError("Wrong national scope or withheld benchmark contract")
    aggregate_counts={k:count(v) for k,v in (
        ("worse",worse),("same",same),("better",better),("too_few",too_few))}
    distinctions=Counter()
    for measure,label,denom,point,lower,upper,flag,*window in providers:
        if measure!=MEASURE or tuple(window)!=PERIOD:
            raise ValueError("Wrong provider program or performance period")
        if point==MISSING:
            expected="Number of cases too small" if flag=="1" else MISSING
            if flag not in FLAGS or label!=expected or any(v!=MISSING for v in (denom,lower,upper)):
                raise ValueError("Ambiguous unavailable display")
            distinctions[FLAGS[flag]]+=1
        else:
            if flag or count(denom)<=0 or not number(lower)<=number(point)<=number(upper):
                raise ValueError("Inconsistent reported numeric display")
            distinctions["numeric_with_reported_interval"]+=1
    return {"national_rows_verified":1,"provider_preview_rows_verified":len(providers),
            "national_rate_status":"source_not_available_not_zero",
            "national_reported_category_counts":aggregate_counts,
            "provider_preview_score_dispositions":dict(distinctions),
            "national_rate_inferred":False,"national_counts_used_as_provider_denominator":False,
            "provider_records_emitted":0,"cross_program_links":0}
