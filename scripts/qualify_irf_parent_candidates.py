"""Offline IRF parent certification candidates using existing public projections.
No confirmed parent, property, operational status or new public row data.
CMS SOM chapter 2 sections 2779A1, 2779C, 2779C1 (Rev. 198).
"""
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    "rehabilitation": ("009eca9c0400521f8547bc542fa51cadb85be317", "2026-09-23", 1222),
    "hospital": ("b0f0c73946064b5cb754912f685d2fcf975fb02b", "2026-11-12", 5435),
    "long-term-hospital": ("4e7e88646adba0076bb6c46e1bd9bfedfa280e48", "2026-09-23", 311),
}
EXTENDED = {"A":"20","B":"21","C":"22","E":"33","F":"40","G":"41","H":"42","J":"43","K":"44"}
FIELDS = ("state", "address", "city", "zip")
REFERENCE = "https://www.cms.gov/regulations-and-guidance/guidance/manuals/downloads/som107c02.pdf"

def candidate(token):
    if re.fullmatch(r"[0-9]{6}", token):
        return ("numeric_rehab" if 3025 <= int(token[2:]) <= 3099 else "numeric_other"), None
    if re.fullmatch(r"[0-9]{2}R3[0-9]{2}", token):
        return "R", token[:2]+"1"+token[3:]
    if re.fullmatch(r"[0-9]{2}T[0-9]{3}", token):
        return "T", token[:2]+"0"+token[3:] if 1 <= int(token[3:]) <= 879 else None
    if re.fullmatch(r"[0-9]{2}T[ABCEFGHJK][0-9]{2}", token):
        return "extended_"+token[3], token[:2]+EXTENDED[token[3]]+token[4:]
    if re.fullmatch(r"[0-9]{2}T[ABCEFGHJK][0-9]{3}", token):
        return "extended_nonstandard_length", None
    return "unresolved", None

def equal(a, b, fields):
    return all(isinstance(a.get(k), str) and a[k].strip() and a[k] == b.get(k) for k in fields)

def screen(irf, parents):
    idx = defaultdict(list)
    for row in parents:
        idx[row["ccn"]].append(row)
    counts, shapes, by_shape = Counter(), Counter(), defaultdict(Counter)
    seen = set()
    for row in irf:
        token = row["ccn"]
        if not isinstance(token, str) or not token or token in seen:
            raise ValueError("invalid or duplicate IRF source token")
        seen.add(token)
        kind, key = candidate(token)
        if kind in ("numeric_rehab", "numeric_other"):
            status = "not_unit"
        elif key is None:
            status = "no_reviewed_rule"
        else:
            matches = idx.get(key, [])
            same = [x for x in matches if equal(x,row,("state",))]
            good = [x for x in same if equal(x,row,FIELDS)]
            exact = [x for x in good if equal(x,row,FIELDS+("name",))]
            if not matches: status = "no_directory_candidate"
            elif not same: status = "state_conflict"
            elif len(same)>1: status = "multiple_directory_records"
            elif len(exact)==1: status = "same_state_address_name"
            elif len(good)==1: status = "same_state_address_name_differs"
            else: status = "same_state_context_differs"
        counts[status]+=1
        shapes[kind]+=1
        by_shape[kind][status]+=1
    if sum(counts.values()) != len(irf) or sum(shapes.values()) != len(irf):
        raise ValueError("aggregate reconciliation")
    return {"counts":dict(counts),"shapes":dict(shapes),
            "byShape":{k:dict(v) for k,v in by_shape.items()},
            "rows":len(irf),"parentRows":len(parents)}

def load(name):
    sha, release, count = PINS[name]
    data = (ROOT/"web/public-directory"/(name+".json")).read_bytes()
    if hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()!=sha:
        raise ValueError("projection blob drift")
    doc=json.loads(data)
    if doc["source"]!=name or doc["release"]!=release or doc["row_count"]!=count or len(doc["records"])!=count:
        raise ValueError("projection metadata drift")
    return doc["records"]

def audit():
    return screen(load("rehabilitation"),load("hospital")+load("long-term-hospital"))

if __name__ == "__main__":
    print(json.dumps(audit(),sort_keys=True))
