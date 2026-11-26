"""Clinical quality reporting diagnostics only; no property-risk interpretation."""
import argparse,json,re,tempfile
from collections import Counter,defaultdict
from decimal import Decimal
from pathlib import Path
from restore_snapshot import LOCK,load_lock,materialize,verify_raw
from remaining_raw_field_profile import csv_rows,HEADERS
DIALYSIS_MEASURES={6:[5],27:[29],34:[36],41:[43],48:[50],55:[57],61:[63],68:[70],75:[77],82:[84],89:[90],94:[96],100:[101],102:[105],106:[109],110:[113],114:[117],119:[118],121:[120],123:[126],127:list(range(130,135)),135:[138],139:[142],143:[146]}
DIALYSIS_INTERVALS=[(n,n+2,n+1) for n in (29,36,43,50,57,63,70,77,84,90,96)]
def need(ok,msg):
    if not ok:raise ValueError(msg)
def numeric(s):
    s=s.strip()
    return Decimal(s) if re.fullmatch(r"[+-]?[0-9]{1,15}(?:\.[0-9]{1,12})?",s) else None
def state(s):
    if not s.strip():return "blank"
    return "numeric" if numeric(s) is not None else "other_nonblank"
def code(s):
    s=s.strip()
    return s if re.fullmatch(r"[0-9]{1,3}",s) else "blank" if not s else "other_nonblank"
def footnote(s):
    # No free text or individual values retained.
    return "blank" if not s.strip() else "numeric_code_or_sequence" if re.fullmatch(r"[0-9]+(?:\s*[,;]\s*[0-9]+)*",s.strip()) else "text_or_other"
def interval(m,l,u):
    a,b,c=map(numeric,(m,l,u))
    if None in (a,b,c):return "incomplete_or_nonnumeric"
    return "ordered_and_contains_estimate" if b<=a<=c else "ordered_estimate_outside" if b<=c else "reversed_bounds"
def fraction(n,d):
    a,b=map(numeric,(n,d))
    if None in (a,b):return "incomplete_or_nonnumeric"
    if a<0 or b<0 or a>b:return "outside_count_relationship"
    return "zero_denominator" if b==0 else "nonnegative_numerator_within_positive_denominator"
def audit(key,h,rows):
    field_counts=defaultdict(Counter); cross=defaultdict(Counter); n=0
    foots=[i+1 for i,f in enumerate(h) if "footnote" in f.casefold()]
    if key=="dialysis":
        need(set(DIALYSIS_MEASURES)=={i+1 for i,f in enumerate(h) if "availability code" in f.casefold()},"dialysis availability fields changed")
    if key=="home-health":
        for i in range(18,70,4):
            need(h[i-1].startswith("Numerator for ") and h[i].startswith("Denominator for ") and "footnote" in h[i+2].casefold(),"home health measure group drift")
        for i,p in ((70,"DTC"),(78,"PPR"),(86,"PPH")):need(h[i-1]==p+" Numerator" and h[i+2]==p+" Risk-Standardized Rate","home health claims group drift")
    for row in rows:
        need(len(row)==len(h),"row width drift");n+=1
        def v(i):return row[i-1]
        for i in foots:field_counts[h[i-1]][footnote(v(i))]+=1
        if key=="dialysis":
            for i,measures in DIALYSIS_MEASURES.items():
                c=code(v(i));field_counts[h[i-1]][c]+=1
                for m in measures:cross[h[m-1]+" | availability"][c+" | "+state(v(m))]+=1
            for m,l,u in DIALYSIS_INTERVALS:cross[h[m-1]+" | confidence interval"][interval(v(m),v(l),v(u))]+=1
        elif key=="home-health":
            for i in range(18,70,4):
                cross[h[i+1]+" | denominator check"][fraction(v(i),v(i+1))]+=1
                cross[h[i+1]+" | reporting"][state(v(i+2))+" | "+footnote(v(i+3))]+=1
            for i in (70,78,86):
                cross[h[i+2]+" | denominator check"][fraction(v(i),v(i+1))]+=1
                cross[h[i+2]+" | confidence interval"][interval(v(i+3),v(i+4),v(i+5))]+=1
                cross[h[i+2]+" | reporting"][state(v(i+3))+" | "+footnote(v(i+7))]+=1
        elif key=="hospital":
            for i in (15,21,27,33,36):
                g,f=map(numeric,(v(i),v(i+1)))
                cross[h[i-1]+" | count comparison"]["incomplete_or_nonnumeric" if None in (g,f) else "facility_count_within_group" if 0<=f<=g else "outside_count_relationship"]+=1
                if i in (15,21,27):
                    parts=[numeric(v(i+j)) for j in (2,3,4)]
                    cross[h[i-1]+" | component comparison"]["incomplete_or_nonnumeric" if f is None or None in parts else "components_equal_facility_count" if sum(parts)==f else "components_differ"]+=1
            cross["Overall rating | reporting"][state(v(13))+" | "+footnote(v(14))]+=1
        elif key=="nursing":
            for i in (34,36,38,40,42,44):cross[h[i-1]+" | reporting"][state(v(i))+" | "+footnote(v(i+1))]+=1
    need(all(sum(c.values())==n for c in list(field_counts.values())+list(cross.values())),"aggregate reconciliation failed")
    return {"rows":n,"field_counts":field_counts,"cross_checks":cross}
def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path);a=p.parse_args()
    pins={x["key"]:x for x in load_lock(LOCK)["sources"]};headers={x["source"]:x for x in json.loads(HEADERS.read_text())["sources"]};out={}
    for key in ("hospital","nursing","dialysis","home-health"):
        pin=pins[key];h=headers[key];need(h["source_sha256"]==pin["sha256"],"header provenance")
        with tempfile.TemporaryDirectory() as d:
            path=materialize(pin,a.raw_dir,Path(d),a.download);rows=csv_rows(path,pin)
            try:
                header=next(rows);need(header==[f["field"] for f in h["fields"]],"header drift")
                result=audit(key,header,rows)
            finally:rows.close()
            verify_raw(path,pin)
        need(result["rows"]==pin["stored_rows"],"source count drift")
        out[key]={"sha256":pin["sha256"],"release":pin["release"],**result}
    result={"sources":out,"limits":"Code spellings retained exactly. Footnotes presence/shape only; no free-text retention. Count relationships and interval containment are diagnostics, not universal quality rules or proof of erroneous source values. No risk score or production approval."}
    with a.output.open("x") as f:json.dump(result,f,indent=2,sort_keys=True)
    print("CLINICAL_MEASURE_QUALITY",json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
