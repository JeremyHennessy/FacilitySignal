"""Independent offline count-only replay; no identifiers/cell values in output."""
from collections import Counter,defaultdict
from datetime import datetime,date
from decimal import Decimal
from hashlib import file_digest
from pathlib import Path
from zipfile import ZipFile
from io import TextIOWrapper
import csv,json,re,sys
p=Path(sys.argv[1]); sha="d34ae917f2da83e25c668547589c6da0044fd5852eea8f6bb16567205371d253"
with p.open("rb") as f: assert p.stat().st_size==90890707 and file_digest(f,"sha256").hexdigest()==sha
def items(z,part):
    with TextIOWrapper(z.open(f"SNF24_2025_{part}.csv"),encoding="latin-1",newline="") as f:
        yield from csv.reader(f,strict=True)
pat=re.compile(r"-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)\Z")
cols=("00100","00200","00300","00400","00500")
labels=("employee_wages","contract_labor","labor_subtotal","nonlabor","unadjusted_subtotal")
outer=Counter(); idcells=defaultdict(lambda:defaultdict(list)); amounts=defaultdict(lambda:defaultdict(list)); sub=set()
with ZipFile(p) as z:
    assert len(z.infolist())==4 and {x.filename:(x.file_size,x.CRC) for x in z.infolist()}=={
        "SNF24_2025_alpha.csv":(140158016,0xc35c5b3e),"SNF24_2025_nmrc.csv":(404092246,0xc472c8f7),
        "SNF24_2025_rollup.csv":(17865554,0x19747188),"SNF24_2025_rpt.csv":(1150371,0xcf424441)}
    hdr={}
    for x in items(z,"rpt"):
        assert len(x)==18 and x[0] not in hdr
        hdr[x[0]]=x[2],x[5],x[6]
    for key,sheet,line,col,x in items(z,"alpha"):
        outer["alpha"]+=1
        if sheet=="S200000" and (line,col) in {("00300","00300"),("00900","00100"),("00900","00200")}:
            assert key in hdr
            idcells[key][(line,col)].append(x)
    for key,sheet,line,col,raw in items(z,"nmrc"):
        outer["numeric"]+=1
        if key not in hdr: outer["orphan_numeric"]+=1
        if sheet!="A000000": continue
        outer["A000000"]+=1
        if not re.fullmatch(r"[0-9]{5}",line) or not re.fullmatch(r"[0-9]{5}",col):
            outer["nonstandard_coordinate_in_A"]+=1
        if not line.startswith("005"):continue
        if line!="00500":
            outer["line5_subscript_rows"]+=1
            sub.add(key)
            continue
        if col in cols: amounts[key][col].append(raw); outer["line5_base_projected_rows"]+=1
assert len(hdr)==11802 and outer["alpha"]==3581725
by=defaultdict(lambda:{"cells":{label:Counter() for label in labels},"eq12_to_3":Counter(),
                       "eq34_to_5":Counter(),"eq124_to_5":Counter(),"presence":Counter()})
def observed(vals):
    if len(vals)>1: return None,"duplicate"
    if not vals: return None,"absent"
    raw=vals[0]
    if not pat.fullmatch(raw):return None,"invalid"
    n=Decimal(raw)
    return n, ("zero" if not n else "positive" if n>0 else "negative")+("_fraction_shape" if "." in raw else "_integer_shape")
def calcs(z,ins,out):
    if all(k in z for k in (*ins,out)):
        return "exact" if sum(z[k] for k in ins)==z[out] else "unequal"
    if out in z and all(z[k] is not None for k in z) and any(k not in z for k in ins):
        return "incomplete_parts_residual_zero" if sum(z[k] for k in ins if k in z)==z[out] else "incomplete_parts_residual_nonzero"
    return "incomplete"
for key,(ccn,b,e) in hdr.items():
    idv=idcells[key]
    d=datetime.strptime(e,"%m/%d/%Y").date(); start=datetime.strptime(b,"%m/%d/%Y").date()
    expected=[("00300","00300",ccn),("00900","00100",b),("00900","00200",e)]
    linked=re.fullmatch(r"[0-9]{6}",ccn) and start<d and d>=date(2025,9,30) and all(idv[(l,c)]==[v] for l,c,v in expected)
    rev=("rev3" if d>=date(2026,6,30) else "pre_rev3") if linked else "identity_or_period_hold"
    o=by[rev]; o["report_count"]=o.get("report_count",0)+1
    if key in sub: o["subscript_held_reports"]=o.get("subscript_held_reports",0)+1
    obs={}
    for i,(col,label) in enumerate(zip(cols,labels),1):
        num,status=observed(amounts[key].get(col,()))
        o["cells"][label][status]+=1
        if num is not None: obs[i]=num
    o["presence"]["".join(str(x) for x in obs) or "none"]+=1
    if not linked or key in sub: continue
    for name,ins,out in (("eq12_to_3",(1,2),3),("eq34_to_5",(3,4),5),("eq124_to_5",(1,2,4),5)):
        missing=(i for i in (*ins,out) if i not in obs)
        if any(amounts[key].get(cols[i-1]) for i in missing):
            o[name]["withheld_invalid_or_duplicate"]+=1
        else: o[name][calcs(obs,ins,out)]+=1
print(json.dumps({"archive_sha256":sha,"rows":outer,"line5":by},sort_keys=True,indent=2))
