"""Read-only reconciliation of the pinned FacilitySignal archive inventory.
No writes, deletes, source retrieval, public-pack changes or pointer promotion.
Metadata mode checks completion receipts, sizes, exact list/HEAD inventory and
stable ETags; full mode additionally streams SHA-256 for every pinned payload.
"""
import argparse,json,os,re
from pathlib import Path
import azure_national_archive as a
from scripts import azure_verified_extension as ext, azure_source_archive as src
from scripts.recover_azure_extension import validate_receipt,load_pin
from scripts.azure_inventory import verify_inventory
from build_combined import require

ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"research/azure_archive_inventory_20261126.json"

class ReadOnlyAzure(src.SourceAzure):
    def blob(self,name):
        if name==ext.EXT_POINTER or "/releases/extension-" in name:
            ext.extension_name(name)
            return self.container.get_blob_client(name)
        return super().blob(name)
    def list(self,prefix):
        if prefix.startswith(src.PREFIX+"/"):
            src.safe(prefix,directory=True)
        elif "/releases/extension-" in prefix:
            ext.extension_name(prefix)
        else:
            a.allowed_name(prefix)
        for p in self.container.list_blobs(name_starts_with=prefix+"/",include=["metadata"]):
            yield {"name":p.name,"bytes":p.size,"etag":str(p.etag),"folder":str((p.metadata or {}).get("hdi_isfolder","")).lower()=="true"}
    def create(self,*args,**kwargs):
        raise ValueError("read-only inventory")
    def delete_probe(self,*args,**kwargs):
        raise ValueError("read-only inventory")

def observation_count(rec):
    s=rec["summary"]
    for field in ("source_observations","organization_observations","organization_role_rows","stored_rows","stored_candidate_rows"):
        if field in s:
            n=s[field]
            require(type(n) is int and n>0,"invalid observation count")
            return n
    raise ValueError("unrecognized source count")

def totals(ledger):
    layers=ledger["layers"]; receipts=ledger["receipts"]
    require(ledger["format_version"]==1 and [x["key"] for x in layers]==["national","extension"],"ledger layer scope")
    require(len({(x["key"],x["source_sha256"]) for x in receipts})==len(receipts),"duplicate source version")
    for x in receipts:
        src.prefix_for(x["key"],x["source_sha256"])
        require(x["kind"] in ("publisher","derived") and (x["key"]=="pecos-nppes-identity-candidates")== (x["kind"]=="derived"),"source grain")
        require(len(x["files"])==2 and {f["path"] for f in x["files"]}=={"projection.sqlite3","audit.json"},"receipt payload scope")
        require(type(x["observations"]) is int and x["observations"]>0,"source count")
        for f in x["files"]:
            require(type(f["bytes"]) is int and f["bytes"]>0 and re.fullmatch(r"[a-f0-9]{64}",f["sha256"]),"payload pin")
    result={"publisher_releases":sum(x["source_releases"] for x in layers)+sum(x["kind"]=="publisher" for x in receipts),
            "source_observations":sum(x["observations"] for x in layers)+sum(x["observations"] for x in receipts if x["kind"]=="publisher"),
            "derived_candidate_observations":sum(x["observations"] for x in receipts if x["kind"]=="derived"),
            "payload_files":sum(x["files"] for x in layers)+sum(len(x["files"]) for x in receipts),
            "payload_bytes":sum(x["payload_bytes"] for x in layers)+sum(f["bytes"] for x in receipts for f in x["files"])}
    require(result==ledger["totals"],"ledger total drift")
    return result

def verify_files(store,prefix,files,full):
    etags={}
    for f in files:
        name=prefix+"/"+f["path"]
        h=store.head(name)
        require(h["bytes"]==f["bytes"],"payload size mismatch")
        etags[name]=a.verify(store,name,f) if full else h["etag"]
    verify_inventory(store,prefix,files,etags)

def source_matches(rec,pin,national):
    require(rec["status"]=="COMPLETE" and rec["domain"]=="FACILITYSIGNAL_PRIVATE_SOURCE" and rec["format_version"]==1 and rec["projector_version"]==1,"source receipt scope")
    require(rec["key"]==pin["key"] and rec["source_sha256"]==pin["source_sha256"] and rec["payload_prefix"]==src.prefix_for(pin["key"],pin["source_sha256"])+"/files","source receipt identity")
    require(rec["base_receipt_sha256"]==pin["base_receipt_sha256"]==national["receipt_sha256"] and rec["base_release"]==national["pointer"]["release"],"source base lineage")
    require(rec["files"]==pin["files"] and rec["total_bytes"]==sum(f["bytes"] for f in pin["files"]),"source payload drift")
    require(rec["sha256_readback"] is True and rec["public_promotion"] is False and observation_count(rec)==pin["observations"],"source count or qualification drift")
    require((rec["publisher"].get("kind")=="derived_identity_candidate_release")== (pin["kind"]=="derived"),"derived/publisher mismatch")

def verify_archive(store,ledger,full=False):
    result=totals(ledger)
    national=ext.national_manifest(store)
    pointer,psha,phead=ext.read_small(store,ext.EXT_POINTER)
    require(pointer["format_version"]==1 and pointer["domain"]==ext.EXT_DOMAIN and pointer["release"]==ledger["layers"][1]["release"] and pointer["base_receipt_sha256"]==national["receipt_sha256"],"extension pointer mismatch")
    expected=ext.archive.PREFIX+"/releases/"+pointer["release"]+"/complete.json"
    require(pointer["receipt"]==expected,"extension receipt path")
    er,_,_=ext.read_small(store,expected,pointer["receipt_sha256"])
    validate_receipt(er,national,load_pin())
    for pin,rec in zip(ledger["layers"],(national["receipt"],er)):
        require(rec["release"]==pin["release"] and rec["source_records"]==pin["observations"] and rec["file_count"]==pin["files"] and rec["total_bytes"]==pin["payload_bytes"],"layer receipt drift")
        verify_files(store,rec["payload_prefix"],rec["files"],full)
    for pin in ledger["receipts"]:
        name=src.prefix_for(pin["key"],pin["source_sha256"])+"/complete.json"
        rec,digest,head=ext.read_small(store,name)
        source_matches(rec,pin,national)
        verify_files(store,rec["payload_prefix"],rec["files"],full)
        require(ext.read_small(store,name,digest)[2]==head,"source receipt changed")
    ext.unchanged(store,national)
    require(ext.read_small(store,ext.EXT_POINTER,psha)[2]==phead,"extension pointer changed")
    return {"status":"PASS","scope":"pinned completed archive only","totals":result,"mode":"full_sha256" if full else "metadata_inventory","payload_sha256_recomputed":full,"national_and_extension_pointers_unchanged":True,"writes":0,"public_promotion":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("--receipt",type=Path,required=True);p.add_argument("--full",action="store_true");args=p.parse_args()
    require(not args.receipt.exists(),"receipt exists");a.run_key(os.environ)
    store=ReadOnlyAzure(os.environ)
    try:result=verify_archive(store,json.loads(LEDGER.read_text()),args.full)
    finally:store.close()
    with args.receipt.open("xb") as out:out.write(a.encode(result))
    print("FACILITYSIGNAL_CONSOLIDATED_ARCHIVE_VERIFIED",json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":main()
