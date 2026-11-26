"""Requalify only the two failed clinics against their exact prior publisher bytes."""
import argparse,json,tempfile
from pathlib import Path
from scripts.qualify_qcor_expansion import download,inspect
from build_combined import require

PINS={
    "rhc":("6bc5ea259da6149770068d823f8223704e05e6505032d7b0528aa98bc3a66fc1",16481),
    "fqhc":("058bd6dbe8dafcb775d1c7eda09fb225197627b4a1a821d3906a65959a63c4ea",875),
}
def main():
    p=argparse.ArgumentParser();p.add_argument("--source",choices=PINS,required=True);p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"audit exists")
    pin,n=PINS[a.source]
    with tempfile.TemporaryDirectory(prefix="qcor-clinic-key-") as d:
        path=Path(d)/"source.xlsx";meta=download(a.source,path)
        require(meta["sha256"]==pin,"source changed; new release review needed")
        result=inspect(path,a.source)
    result.update({"source":meta,"reuse_review":"pending","prior_run":45827150713,"diagnostic_run":45827628592,
      "key_reference":"https://www.cms.gov/files/document/r226soma.pdf","same_release_verified":True})
    with a.audit.open("x") as f:json.dump(result,f,indent=2);f.write("\n")
    print("QCOR_CLINIC_REQUALIFICATION",json.dumps(result),flush=True)
    require(result["mapping_complete"] and result["input_rows"]==n==result["stored_rows"] and result["rejected_rows"]==0,"remaining source anomalies")
if __name__=="__main__":main()
