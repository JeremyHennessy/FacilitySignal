"""Diagnose dialysis address discrepancies without promoting any identity joins.

Only exact CCN + expected ESRD scope candidates are compared. All identifying
values remain ephemeral; output contains aggregate counts only.
"""
import argparse,csv,json,re,tempfile
from collections import Counter,defaultdict
from pathlib import Path
from restore_snapshot import LOCK,load_lock,materialize,verify_raw
from collect_registry import open_csv,source_encoding
from probe_pos_fields import INVENTORY
from scripts.qualify_dialysis_service_projection import load_public,corroboration,norm,zip5,ROOT
SUFFIX={"street":"st","avenue":"ave","road":"rd","boulevard":"blvd","drive":"dr","lane":"ln","court":"ct","place":"pl","highway":"hwy","parkway":"pkwy","circle":"cir","terrace":"ter","trail":"trl"}
DIRECTION={"north":"n","south":"s","east":"e","west":"w","northeast":"ne","northwest":"nw","southeast":"se","southwest":"sw"}
def need(ok,msg):
    if not ok:raise ValueError(msg)
def punctuation(value):
    # Remove periods after standalone alphabetic tokens; never alter number
    # punctuation, hyphens, slashes, unit identifiers, or token order.
    return " ".join(re.sub(r"(?<![\w])([a-z]+)\.(?=\s|$)",r"\1",norm(value)).split())
def street(value):
    t=punctuation(value).split()
    if len(t)>=3 and re.fullmatch(r"[0-9]+[a-z]?",t[0]):
        # Only terminal street suffix, or suffix immediately before a
        # terminal direction. Unit-bearing strings remain conservative.
        i=-2 if t[-1] in set(DIRECTION)|set(DIRECTION.values()) else -1
        if t[i] in SUFFIX:t[i]=SUFFIX[t[i]]
        if t[-1] in DIRECTION and i==-2 and t[i] in SUFFIX.values():t[-1]=DIRECTION[t[-1]]
    return " ".join(t)
def agreement(a,b):
    return "missing" if not a or not b else "equal" if a==b else "differs"
def detail(p,r):
    state=agreement(norm(p["state"]),norm(r["state_cd"]))
    city=agreement(norm(p["city"]),norm(r["city_name"]))
    z=agreement(zip5(p["zip"]),zip5(r["zip_cd"]))
    a,b=p["address"],r["st_adr"]
    raw=agreement(norm(a),norm(b))
    if raw!="differs":stage=raw
    elif punctuation(a)==punctuation(b):stage="punctuation_only"
    elif street(a)==street(b):stage="suffix_or_terminal_direction"
    else:stage="unresolved_street"
    return state,city,z,stage
def audit(rows,public):
    hits=defaultdict(list);n=esrd=0
    for r in rows:
        n+=1
        need(None not in r and all(v is not None for v in r.values()),"malformed registry record")
        t=r["prvdr_type_id"].strip()
        if not re.fullmatch(r"[0-9]{1,3}",t) or int(t)!=7:continue
        esrd+=1
        ident=r["prvdr_num"].strip()
        if ident in public:hits[ident].append(r)
    old=Counter();joint=Counter();new=Counter()
    for ident,p in public.items():
        rows=hits.get(ident,[])
        if not rows:old["no_esrd_identifier_candidate"]+=1;continue
        if len(rows)!=1:old["multiple_esrd_identifier_candidates"]+=1;continue
        r=rows[0];old_state=corroboration(p,r);old[old_state]+=1
        s,c,z,a=detail(p,r);joint["|".join((s,c,z,a))]+=1
        if old_state=="corroborated":new["existing_strict_corroboration"]+=1
        elif (s,c,z)==("equal","equal","equal") and a in ("punctuation_only","suffix_or_terminal_direction"):
            new["formatting_candidate_"+a]+=1
        else:new["unresolved_unique_candidate"]+=1
    need(sum(old.values())==len(public),"provider reconciliation")
    need(sum(joint.values())==sum(new.values())==sum(v for k,v in old.items() if k not in ("no_esrd_identifier_candidate","multiple_esrd_identifier_candidates")),"unique candidate reconciliation")
    return {"registry_rows":n,"esrd_rows":esrd,"public_rows":len(public),"prior_dispositions":old,"unique_candidate_joint_agreement":joint,"normalization_diagnostic":new}
def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);p.add_argument("--download",action="store_true");p.add_argument("--raw-dir",type=Path);a=p.parse_args()
    pin=next(s for s in load_lock(LOCK)["sources"] if s["key"]=="iqies")
    prior=json.loads((ROOT/"research/dialysis_service_public_audit_20261126.json").read_text())
    public,digest=load_public()
    need(digest==prior["public_dialysis_sha256"] and pin["sha256"]==prior["source_sha256"],"prior provenance drift")
    inv=json.loads(INVENTORY.read_text())["registries"]["iqies"]
    need(inv["source_sha256"]==pin["sha256"],"inventory drift")
    with tempfile.TemporaryDirectory() as d:
        path=materialize(pin,a.raw_dir,Path(d),a.download)
        with open_csv(path,pin["metadata"]["zipped"],source_encoding(path,pin["metadata"]["zipped"])) as f:
            r=csv.DictReader(f,strict=True)
            need(r.fieldnames==[x["field"] for x in inv["fields"]],"header drift")
            out=audit(r,public)
        verify_raw(path,pin)
    need(out["registry_rows"]==prior["registry_rows"] and out["esrd_rows"]==prior["esrd_source_rows"],"source scope drift")
    need(dict(out["prior_dispositions"])==prior["match_dispositions"],"prior match count drift")
    out.update(source_sha256=pin["sha256"],source_period=pin["release"],public_sha256=digest,limits="Diagnostic only. Normalized equality does not establish same physical site. No candidate promotion, address values, identifiers, or production mapping changes.")
    with a.output.open("x") as f:json.dump(out,f,indent=2,sort_keys=True)
    print("DIALYSIS_ADDRESS_EVIDENCE",json.dumps(out,sort_keys=True))
if __name__=="__main__":main()
