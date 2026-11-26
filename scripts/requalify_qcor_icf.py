"""Requalify ICF-IID on the exact prior release; aggregate shape diagnostics."""
import argparse,hashlib,json,tempfile
from collections import Counter
import re
from pathlib import Path
from scripts.qualify_qcor_expansion import download,inspect
from build_combined import require
from scripts.probe_qcor_icf_tag_domain import fetch_domain
PIN="4522aff6cf8242a7315814d1629c58729c2a17971038b51a3e717780ca8e4dda"
ROWS=385312
def main():
    p=argparse.ArgumentParser();p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    domains,selector=fetch_domain()
    require(len(domains)==1,"ambiguous publisher tag selector")
    domain=domains[0]
    families=dict(Counter(re.match(r"[A-Z]+",code).group() for code in domain))
    require(families=={"E":25,"K":118,"KA":31,"KL":46,"KS":47,"W":372},"publisher tag domain changed; review before workbook retrieval")
    domain_sha=hashlib.sha256("\n".join(sorted(domain)).encode()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="qcor-icf-tags-") as d:
        path=Path(d)/"source.xlsx";meta=download("icf",path)
        require(meta["sha256"]==PIN,"source changed; review new release")
        result=inspect(path,"icf",domain)
    result.update({"source":meta,"reuse_review":"pending","prior_run":45827150713,
                   "same_release_verified":True,"publisher_selector":selector,"publisher_code_domain_sha256":domain_sha,"publisher_code_domain_size":len(domain),"domain_probe_run":45829724547,"tag_format_reference":["https://qcor.cms.gov/ICF-IID_2567_Reports?page=6116","https://qcor.cms.gov/ICF-IID_2567_Reports?page=1"]})
    with a.audit.open("x") as f:json.dump(result,f,indent=2);f.write("\n")
    print("QCOR_ICF_REQUALIFICATION",json.dumps(result),flush=True)
    require(result["mapping_complete"] and result["input_rows"]==ROWS==result["stored_rows"] and result["rejected_rows"]==0,"remaining source anomalies")
if __name__=="__main__":main()
