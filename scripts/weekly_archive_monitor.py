"""Check publisher metadata and exact pinned source receipts. Review changed
sources rather than assuming new projections have passed qualification."""
import json,urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from build_combined import require
from scripts import azure_source_archive as src
from scripts.azure_verified_extension import read_small
from scripts.audit_azure_archive_inventory import source_matches,LEDGER
from scripts import archive_environment_state as state, archive_hcris_form_indexes as forms
from probe_ownership import select
import collect_registry as registry

def head_metadata(url):
    p=urlsplit(url)
    require(p.scheme=="https" and p.hostname in {"www.cms.gov","downloads.cms.gov","echo.epa.gov"},"monitor source host")
    req=urllib.request.Request(url,method="HEAD",headers={"User-Agent":"FacilitySignal metadata monitor"})
    with urllib.request.urlopen(req,timeout=45) as r:
        require(urlsplit(r.geturl()).hostname==p.hostname,"monitor redirect host")
        return {"etag":r.headers.get("ETag"),"last_modified":r.headers.get("Last-Modified"),"bytes":int(r.headers["Content-Length"]) if r.headers.get("Content-Length") else None}

def compare_metadata(old,new,fields):
    comparable=[k for k in fields if old.get(k) is not None and new.get(k) is not None]
    if not comparable:return "metadata_review"
    if any(old[k]!=new[k] for k in comparable):return "new_version_review"
    return "metadata_unchanged" if len(comparable)==len([k for k in fields if old.get(k) is not None]) else "metadata_review"

def monitor(store,national):
    ledger=json.loads(LEDGER.read_text());results={};catalog=None
    pins=[p for p in ledger["receipts"] if p["key"] not in {"nppes-monthly","nppes-weekly","pecos-nppes-identity-candidates"} and p["kind"]!="supplemental_numeric"]
    require(len(pins)<=100,"archive monitoring bound")
    for pin in pins:
        key=pin["key"];ident=key+":"+pin["source_sha256"][:12]
        try:
            rec,_,_=read_small(store,src.prefix_for(key,pin["source_sha256"])+"/complete.json")
            source_matches(rec,pin,national);old=rec["publisher"]
            if old.get("title") and old.get("api") and old.get("period"):
                if catalog is None:catalog=registry.get_json(registry.CATALOG)
                new=select(catalog,old["title"]);n=registry.expected_rows(new)
                outcome=compare_metadata(old,new,("period","api","modified","distributions"))
                expected=rec["summary"].get("input_rows")
                if expected is not None and expected!=n:outcome="new_version_review"
                results[ident]={"state":outcome,"api_count":n,"publisher_period":new["period"]}
            elif key=="ppef-type2-enrollment":
                from scripts.archive_ppef_enrollment import discover
                results[ident]={"state":compare_metadata(old,discover(),("catalog_version","modified","main_file","url","resource_name"))}
            elif key=="wa-xray-aggregate":
                new=state.wa_metadata();results[ident]={"state":compare_metadata(old,new,("rows_updated_at","view_last_modified","count","fields")),"publisher_count":new["count"]}
            elif key.startswith("il-reportcard-"):
                _,hashes=state.il_records(key.removeprefix("il-reportcard-"))
                results[ident]={"state":"metadata_unchanged" if hashes==old["page_sha256"] else "new_version_review","pages_checked":len(hashes)}
            elif key.startswith("hcris-") or key in {"epa-sdwa-aggregate","epa-frs-healthcare-aggregate","epa-rcra-healthcare-aggregate","epa-npdes-part1-healthcare-aggregate"}:
                if key.endswith("-index"):
                    targets=[k for k,v in forms.TARGETS.items() if "hcris-"+v[0]==key]
                    require(len(targets)==1,"monitor form identity")
                    if forms.discover(targets[0])["url"]!=old["url"]:
                        results[ident]={"state":"new_version_review","reason":"publisher_link_changed"};continue
                new=head_metadata(old["url"])
                results[ident]={"state":compare_metadata(old,new,("etag","last_modified","bytes"))}
            else:
                results[ident]={"state":"metadata_review","reason":"no_qualified_adapter_for_monitor"}
        except Exception as e:results[ident]={"state":"failed","error_type":type(e).__name__}
    return results
