"""Stage only the independently qualified public institutional flags.

No production publication, private-only fields, publisher downloads or Azure
writes. A second, credential-free job validates and creates a candidate branch.
"""
import argparse
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path

import azure_national_archive as archive
from build_combined import require, sha
from scripts import audit_azure_archive_inventory as inventory
from scripts import institutional_search as search
from scripts.public_identity_candidate_audit import load as load_directories

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/"docs/institutional_search_receipt_20261126.json"
# Independent explicit allowlist: never derive release permissions from all
# candidate_field rows or from source schema discovery.
FIELDS={
    "hospital":["emergency_services"],
    "dialysis":["chain_owned_or_managed","late_shift","in_center_hemodialysis","peritoneal_dialysis","home_hemodialysis_training"],
    "nursing":["ownership_change_12_months"],
}
VALUES={"reported_yes","reported_no"}
SCOPE="Candidate public CMS reported institutional flags; historical release, not live service, legal title, risk or compliance."
PACK="institutional-evidence.json"
MANIFEST="institutional-evidence-manifest.json"


def read(path):
    return json.loads(path.read_text())


def validate_pack(pack, expected, directories, pins):
    require(set(pack)=={"format_version","scope","sources"} and pack["format_version"]==1 and pack["scope"]==SCOPE,"candidate scope")
    require(set(pack["sources"])==set(FIELDS),"candidate source scope")
    observed=0
    for source, fields in FIELDS.items():
        data=pack["sources"][source]
        require(set(data)=={"release","source_sha256","directory_sha256","fields","records"},"unexpected candidate property")
        require(data["fields"]==fields,"unapproved or reordered fields")
        pin=pins[source]
        require(data["release"]==pin["release"] and data["directory_sha256"]==pin["sha256"],"directory source drift")
        require(data["source_sha256"]==expected[source]["source_sha256"],"publisher source drift")
        directory_keys={(x["ccn"],x["state"]) for x in directories[source]["records"]}
        seen=set()
        counts={f:Counter() for f in fields}
        for row in data["records"]:
            require(isinstance(row,list) and len(row)==2+len(fields),"unexpected candidate row width")
            ccn, state, *values=row
            require(isinstance(ccn,str) and re.fullmatch("[A-Z0-9]{6}",ccn) and state in search.STATES,"invalid source key")
            require((ccn,state) in directory_keys and (ccn,state) not in seen,"candidate membership or duplicate")
            seen.add((ccn,state))
            for field,value in zip(fields,values):
                require(value in VALUES,"unexpected public flag value")
                counts[field][value]+=1
        require(seen==directory_keys and len(seen)==pin["rows"]==expected[source]["providers"],"missing candidate source records")
        require({f:dict(n) for f,n in counts.items()}=={f:expected[source]["fields"][f] for f in fields},"candidate counts differ")
        observed+=len(seen)*len(fields)
    return observed


def manifest_for(folder):
    evidence=read(EVIDENCE)
    prior=evidence["receipt"]
    require(prior["status"]=="PASS" and prior["public_promotion"] is False and prior["publisher_downloads"]==0 and prior["azure_writes"]==0,"prior qualification receipt scope")
    candidate=folder/PACK
    require(candidate.is_file() and not candidate.is_symlink() and candidate.stat().st_size==prior["candidate_bytes"] and sha(candidate)==prior["candidate_sha256"],"candidate is not exact qualified bytes")
    dirs,pins=load_directories(ROOT)
    expected=read(search.QUAL)["sources"]
    count=validate_pack(read(candidate),expected,dirs,pins)
    require(count==prior["public_candidate_observations"]==57476,"candidate observation total")
    return {"format_version":1,"publisher":"Centers for Medicare & Medicaid Services","source_attribution":"CMS Provider Data Catalog; independent FacilitySignal research, no government endorsement.","scope":"Qualified public candidate for historical institutional flags; not production release.","candidate_sha256":sha(candidate),"candidate_bytes":candidate.stat().st_size,"observations":count,"provider_records":prior["provider_records"],"source_pins":{s:{"release":pins[s]["release"],"directory_sha256":pins[s]["sha256"],"source_sha256":expected[s]["source_sha256"],"fields":FIELDS[s]} for s in sorted(FIELDS)},"qualification_run":evidence["qualification_run"],"public_promotion":False}


def stage(output):
    require(not output.exists(),"candidate output already exists")
    archive.run_key(os.environ)
    store=inventory.ReadOnlyAzure(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="institutional-public-candidate-") as tmp:
            root=Path(tmp)
            result=search.qualify(store,root,root/"qualification.json")
            prior=read(EVIDENCE)["receipt"]
            require(result==prior,"fresh qualification differs from accepted receipt")
            output.mkdir(mode=0o700)
            (output/PACK).write_bytes((root/"candidate.json").read_bytes())
            manifest=manifest_for(output)
            (output/MANIFEST).write_bytes(archive.encode(manifest))
    finally:
        store.close()
    verify(output)
    return manifest


def verify(output):
    require(output.is_dir() and not output.is_symlink() and {p.name for p in output.iterdir()}=={PACK,MANIFEST},"candidate inventory scope")
    expected=manifest_for(output)
    actual=read(output/MANIFEST)
    require(actual==expected,"candidate manifest mismatch")
    return expected


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=("stage","verify"))
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    result=stage(a.output) if a.mode=="stage" else verify(a.output)
    print("FACILITYSIGNAL_INSTITUTIONAL_PUBLIC_CANDIDATE",json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
