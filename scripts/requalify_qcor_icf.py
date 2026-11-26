"""Requalify ICF-IID on the exact prior release; aggregate shape diagnostics."""
import argparse,json,tempfile
from pathlib import Path
from scripts.qualify_qcor_expansion import download,inspect
from build_combined import require
PIN="4522aff6cf8242a7315814d1629c58729c2a17971038b51a3e717780ca8e4dda"
ROWS=385312
def main():
    p=argparse.ArgumentParser();p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    with tempfile.TemporaryDirectory(prefix="qcor-icf-tags-") as d:
        path=Path(d)/"source.xlsx";meta=download("icf",path)
        require(meta["sha256"]==PIN,"source changed; review new release")
        result=inspect(path,"icf")
    result.update({"source":meta,"reuse_review":"pending","prior_run":45827150713,
                   "same_release_verified":True,"tag_format_reference":"https://qcor.cms.gov/ICF-IID_2567_Reports?page=6116"})
    with a.audit.open("x") as f:json.dump(result,f,indent=2);f.write("\n")
    print("QCOR_ICF_REQUALIFICATION",json.dumps(result),flush=True)
    require(result["mapping_complete"] and result["input_rows"]==ROWS==result["stored_rows"] and result["rejected_rows"]==0,"remaining source anomalies")
if __name__=="__main__":main()
