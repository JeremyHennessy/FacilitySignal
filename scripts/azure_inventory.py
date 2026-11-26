"""Compare list/HEAD ETags without weakening byte or conditional-read checks."""
import re
from pathlib import PurePosixPath
from build_combined import require

def etag_relation(listed,head):
    if isinstance(listed,str) and listed and listed==head:return "exact"
    # ETags are opaque. Permit only one optional pair of HTTP double quotes
    # around an otherwise byte-identical Azure-style hex token. Never casefold,
    # strip whitespace, accept weak ETags or equate different underlying values.
    def token(s):
        if not isinstance(s,str):return None
        if re.fullmatch(r'"0x[0-9A-Fa-f]+"',s):return s[1:-1]
        if re.fullmatch(r"0x[0-9A-Fa-f]+",s):return s
        return None
    a,b=token(listed),token(head)
    return "quote_only" if a is not None and a==b else "different"

def verify_inventory(store,prefix,records,head_etags):
    wanted={prefix+"/"+r["path"]:r["bytes"] for r in records}
    require(len(wanted)==len(records) and set(head_etags)==set(wanted),"expected inventory inconsistent")
    parents={str(p) for n in wanted for p in PurePosixPath(n).parents if str(p).startswith(prefix+"/")}
    actual={};seen=set();markers=0
    for v in store.list(prefix):
        name=v["name"]
        require(name.startswith(prefix+"/") and name not in seen,"invalid archive inventory")
        seen.add(name)
        if v.get("folder"):
            require(v["bytes"]==0 and name.rstrip("/") in parents and name not in wanted,"unexpected directory marker")
            markers+=1;continue
        actual[name]=v
    require({k:v["bytes"] for k,v in actual.items()}==wanted,"archive inventory mismatch")
    relation={"exact":0,"quote_only":0,"different":0}
    for name,v in actual.items():
        # Read HEAD again: the exact conditional-read ETag must not drift.
        h=store.head(name)
        require(h=={"bytes":wanted[name],"etag":head_etags[name]},"payload HEAD changed after byte verification")
        relation[etag_relation(v["etag"],h["etag"])]+=1
    result={"files":len(actual),"folder_markers":markers,"list_head_etag_relations":relation}
    print("AZURE_INVENTORY_ETAG_AUDIT",__import__("json").dumps(result,sort_keys=True),flush=True)
    require(relation["different"]==0,"archive ETags differ beyond quoting")
    return result
