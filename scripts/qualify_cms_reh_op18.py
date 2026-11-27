"""Check the two different statistics in the pinned national REH OP-18 display."""
from collections import Counter
import re

EDITION="2026-11-12"
PERIOD=("01/01/2025","12/31/2025")
MEASURES={f"REH_OP_18{g}{suffix}" for g in "abcd" for suffix in ("","_NINETIETH")}

def qualify(rows,release):
    if release!=EDITION or len(rows)!=8 or {r[0] for r in rows}!=MEASURES:
        raise ValueError("Expected eight unique OP-18 fields in exact release")
    values={}
    for ident,label,duration,footnote,start,end in rows:
        if (start,end)!=PERIOD or footnote or not isinstance(duration,str) or not re.fullmatch(r"[0-9]{1,5}",duration):
            raise ValueError("Unexpected performance window, score domain or footnote")
        expected="top ten percent " if ident.endswith("_NINETIETH") else "average (median) "
        if not label.lower().startswith(expected):
            raise ValueError("Missing or conflicting publisher statistic label")
        values[ident]=int(duration)
    order=Counter()
    for g in "abcd":
        base=values[f"REH_OP_18{g}"]
        top=values[f"REH_OP_18{g}_NINETIETH"]
        order["top_label_lower" if top<base else "top_label_equal" if top==base else "top_label_higher"]+=1
    return {"national_display_rows":8,"paired_reporting_populations":4,
            "publisher_statistic_counts":{"median_labeled":4,"top_ten_percent_labeled":4},
            "reported_pair_order_counts":dict(order),"patient_wait_quantiles_derived":0,
            "performance_or_transfer_inferences":0,"app_facility_rows_emitted":0}
