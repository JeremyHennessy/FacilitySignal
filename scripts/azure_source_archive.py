"""Create-only, independently verifiable private source snapshots.

Version key is the exact input SHA, scoped by source and projector version.
Never publish raw data, overwrite national pointers or create public URLs.
"""
import hashlib,json,re
from pathlib import Path
import azure_national_archive as a
from scripts.azure_verified_extension import national_manifest,unchanged,read_small
from scripts.azure_inventory import verify_inventory
from build_combined import require,sha
PREFIX=a.PREFIX+"/source-releases"
KEYS={"hcris-hha-2024","nppes-monthly","nppes-weekly","hha-organizational-ownership","hospice-organizational-ownership","hha-selected-cost-2024","pecos-nppes-identity-candidates","hha-enrollment-organizations","hospice-enrollment-organizations","hcris-hospital-2024-index","hcris-snf-2024-index","hcris-hospice-2014-index","hcris-renal-2011-index","hcris-fqhc-2014-index","hcris-rhc-2017-index","hcris-cmhc-2017-index","ppef-type2-enrollment","epa-sdwa-aggregate","wa-xray-aggregate","il-reportcard-hospitals","il-reportcard-ascs"}
SUPPLEMENTAL_NUMERIC_PARENTS={"hcris-cmhc-2017-numeric":"hcris-cmhc-2017-index","hcris-rhc-2017-numeric":"hcris-rhc-2017-index","hcris-fqhc-2024-numeric":"hcris-fqhc-2014-index","hcris-hospice-2024-numeric":"hcris-hospice-2014-index","hcris-renal-2024-numeric":"hcris-renal-2011-index"}
# Deterministic, nonoverlapping source ordinals for large FY2024 forms.
LARGE_NUMERIC_ROWS={"hospital":19440697,"snf":13769223}
LARGE_NUMERIC_PART_SIZE=3_000_000
LARGE_NUMERIC_SCOPES={}
for form,n in LARGE_NUMERIC_ROWS.items():
    for start in range(1,n+1,LARGE_NUMERIC_PART_SIZE):
        end=min(n,start+LARGE_NUMERIC_PART_SIZE-1)
        key=f"hcris-{form}-2024-numeric-{start:08d}-{end:08d}"
        LARGE_NUMERIC_SCOPES[key]=(form,start,end)
        SUPPLEMENTAL_NUMERIC_PARENTS[key]=f"hcris-{form}-2024-index"
KEYS.update(SUPPLEMENTAL_NUMERIC_PARENTS)
KEYS.add("epa-frs-healthcare-aggregate")
MAX_DB=1_500_000_000
def prefix_for(key,digest):
    require(key in KEYS and re.fullmatch(r"[a-f0-9]{64}",digest),"source release identity")
    return PREFIX+"/"+key+"/v1/"+digest
def safe(name,*,directory=False):
    pattern=re.escape(PREFIX)+r"/(?:"+"|".join(sorted(KEYS))+r")/v1/[a-f0-9]{64}"
    pattern+=r"/files" if directory else r"/(?:files/(?:projection.sqlite3|audit.json)|complete.json)"
    require(re.fullmatch(pattern,name),"source archive write/read boundary")
    return name
class SourceAzure(a.Azure):
    def blob(self,n):
        if n.startswith(PREFIX+"/"):safe(n)
        else:a.allowed_name(n)
        return self.container.get_blob_client(n)
    def create(self,n,stream,size,kind):
        safe(n);return super().create(n,stream,size,kind)
    def delete_probe(self,n,etag):
        raise ValueError("no deletion from source archive")
    def list(self,prefix):
        safe(prefix,directory=True)
        for p in self.container.list_blobs(name_starts_with=prefix+"/",include=["metadata"]):
            yield {"name":p.name,"bytes":p.size,"etag":str(p.etag),"folder":str((p.metadata or {}).get("hdi_isfolder","")).lower()=="true"}
def existing(store,key,source_sha):
    prefix=prefix_for(key,source_sha);name=prefix+"/complete.json"
    if not store.exists(name):return None
    rec,_,_=read_small(store,name)
    require(rec["domain"]=="FACILITYSIGNAL_PRIVATE_SOURCE" and rec["status"]=="COMPLETE" and rec["key"]==key and rec["source_sha256"]==source_sha and rec["projector_version"]==1 and rec["payload_prefix"]==prefix+"/files","prior source receipt mismatch")
    files=rec["files"]
    require(len(files)==2 and {x["path"] for x in files}=={"projection.sqlite3","audit.json"},"prior source inventory")
    etags={}
    for r in files:etags[prefix+"/files/"+r["path"]]=a.verify(store,prefix+"/files/"+r["path"],r)
    verify_inventory(store,prefix+"/files",files,etags)
    store.private()
    return rec
def publish(store,key,meta,db,audit,root,national):
    digest=meta["sha256"];prefix=prefix_for(key,digest);payload=prefix+"/files"
    require(0<db.stat().st_size<=MAX_DB,"projection size bound")
    require(not store.exists(prefix+"/complete.json"),"source release already complete")
    require(audit["projection_sha256"]==sha(db) and audit["projection_bytes"]==db.stat().st_size,"local projection pin mismatch")
    audit_path=root/"audit.json";audit_path.write_bytes(a.encode(audit))
    records=[a.rec("projection.sqlite3",db),a.rec("audit.json",audit_path)]
    files={"projection.sqlite3":db,"audit.json":audit_path};etags={}
    unchanged(store,national)
    for r in records:
        name=payload+"/"+r["path"]
        if not store.exists(name):
            with files[r["path"]].open("rb") as f:store.create(name,f,r["bytes"],"application/json" if name.endswith(".json") else "application/octet-stream")
        etags[name]=a.verify(store,name,r)
        require(sha(files[r["path"]])==r["sha256"],"local payload changed")
    inv=verify_inventory(store,payload,records,etags)
    unchanged(store,national)
    receipt={"format_version":1,"domain":"FACILITYSIGNAL_PRIVATE_SOURCE","status":"COMPLETE","key":key,"projector_version":1,"source_sha256":digest,"publisher":meta,"payload_prefix":payload,"base_release":national["pointer"]["release"],"base_receipt_sha256":national["receipt_sha256"],"files":records,"total_bytes":sum(x["bytes"] for x in records),"sha256_readback":True,"inventory":inv,"summary":audit["summary"],"public_promotion":False,"reuse_review":"pending"}
    a.put_bytes(store,prefix+"/complete.json",a.encode(receipt))
    verify_inventory(store,payload,records,etags)
    unchanged(store,national)
    return receipt
