"""Read the official QCOR report's tag-selector metadata, not facility rows.

Only recognized tag-code option values are inspected. Aggregate code family
counts are retained; no option descriptions, provider values or report HTML.
"""
import argparse,hashlib,json,re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from scripts.probe_qcor_hospital import request
from build_combined import require
URL="https://qcor.cms.gov/ICF-IID_2567_Reports"
LIMIT=5_000_000
class Selects(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.current=None;self.selects=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="select":
            require(self.current is None,"nested selector")
            self.current={"name":a.get("name") or a.get("id") or "","values":[]}
        elif tag=="option" and self.current is not None:
            self.current["values"].append(a.get("value") or "")
    def handle_endtag(self,tag):
        if tag=="select" and self.current is not None:
            self.selects.append(self.current);self.current=None

def analyze(html):
    p=Selects();p.feed(html);p.close()
    found=[];structural=[]
    for s in p.selects:
        name=s["name"]
        # Do not inspect or retain other selectors' values.
        if "tag" not in name.casefold():continue
        codes=set();unknown=0;blank=0
        for raw in s["values"]:
            v=raw.strip().upper()
            if not v:blank+=1;continue
            if re.fullmatch(r"(?:[A-Z][0-9]{4}|[A-Z]{2}[0-9]{3})",v):
                codes.add(v)
            else:unknown+=1
        fam=Counter(re.match(r"[A-Z]+",x).group() for x in codes)
        entry={"option_count":len(s["values"]),"distinct_exact_code_values":len(codes),"blank_options":blank,
               "other_option_count":unknown,"code_family_counts":dict(sorted(fam.items()))}
        structural.append(entry)
        # Validate both previously observed families before using any new domain.
        if fam.get("KS",0) and fam.get("KA",0) and unknown==0:found.append(codes)
    return found,{"selector_count":len(p.selects),"tag_named_selectors":structural,"qualified_selector_candidates":len(found)}

def fetch_domain():
    with request(URL,"text/html") as r:
        require(r.geturl()==URL,"unexpected publisher redirect")
        data=r.read(LIMIT+1)
    require(0<len(data)<=LIMIT,"publisher page bound")
    domains,result=analyze(data.decode("utf-8",errors="strict"))
    result.update({"url":URL,"html_bytes":len(data),"html_sha256":hashlib.sha256(data).hexdigest(),
                   "limits":"Selector metadata only; no HTML, descriptions, facility records or row-level findings retained. Code membership is syntax/domain evidence, not current compliance or a semantic crosswalk."})
    return domains,result
def main():
    p=argparse.ArgumentParser();p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    domains,result=fetch_domain()
    with a.audit.open("x") as f:json.dump(result,f,indent=2);f.write("\n")
    print("QCOR_ICF_TAG_DOMAIN_AUDIT",json.dumps(result),flush=True)
    require(len(domains)==1,"no unambiguous official tag selector; no workbook retrieval")
if __name__=="__main__":main()
