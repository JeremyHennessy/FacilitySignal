"""Opt-in local national recovery of the separately qualified registry projections.

Reuse each registry source in the base recovery loop, before deleting staged raw
bytes. Pin both dictionary documents; never silently update historical semantics.
"""
from contextlib import closing
import sqlite3
from build_combined import require,sha,check_integrity
import iqies_capabilities as iq
import qies_hospital_services as q
import probe_iqies_dictionary as dictionary

def exact_document(raw_dir,stage,name,digest,size,download,allow_download):
    local=raw_dir/name if raw_dir else None
    path=local if local and (local.exists() or local.is_symlink()) else stage/name
    if path!=local:
        require(allow_download,"missing dictionary: "+name)
        download(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size==size and sha(path)==digest,"dictionary bytes changed: "+name)
    return path

def prepare_dictionaries(raw_dir,stage,allow_download):
    x=exact_document(raw_dir,stage,"iqies-dictionary.xlsx",iq.DICT_SHA,iq.DICT_BYTES,dictionary.download,allow_download)
    y=exact_document(raw_dir,stage,"qies-layout.pdf",q.LAYOUT_SHA,q.LAYOUT_BYTES,q.dictionary_evidence,allow_download)
    return {"iqies":x,"qies":y}

def project_one(db_path,item,path,documents):
    key=item["key"]
    require(key in ("iqies","qies") and item["family"]=="registry","unexpected projection source")
    with closing(sqlite3.connect(db_path)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        if key=="iqies":
            return iq.project(db,path,item,documents[key])
        p=documents[key]
        require(p.is_file() and not p.is_symlink() and p.stat().st_size==q.LAYOUT_BYTES and sha(p)==q.LAYOUT_SHA,"QIES layout bytes changed")
        layout={"url":q.LAYOUT_URL,"sha256":q.LAYOUT_SHA,"bytes":q.LAYOUT_BYTES,"document_date":q.LAYOUT_DATE,"catalog_reference_verified_in_run":45700676606}
        return q.project(db,path,item,layout)

def audit_projections(db_path,projections):
    require(set(projections)=={"iqies","qies"},"projection coverage mismatch")
    a,b=projections["iqies"],projections["qies"]
    require(a["source_records_verified"]==100334 and a["provider_scope_rows"]=={"ASC":8492,"ESRD":8659},"iQIES scope baseline mismatch")
    require(a["capability_observations"]==68604 and a["field_states"]["oprtg_room_cnt"].get("unrecognized")==4,"iQIES observations baseline mismatch")
    require(a["count_value_totals"]=={"oprtg_room_cnt":28183,"procedure_room_cnt":1568,"dlys_stn_cnt":134626},"iQIES capacity baseline mismatch")
    require(b["source_records_verified"]==13598 and b["hospital_category_rows"]==13598 and b["service_observations"]==163176,"QIES scope baseline mismatch")
    expected={"CT_SCAN_SRVC_CD":[6773,4127,731,572],"MGNTC_RSNC_IMG_SRVC_CD":[7273,2653,1650,627],"PET_SCAN_SRVC_CD":[10327,686,921,269],"NUCLR_MDCN_SRVC_CD":[5349,4064,2096,694],"DNTL_SRVC_CD":[8860,1225,1858,260],"OPRTG_ROOM_SRVC_CD":[4147,6919,461,676],"DGNSTC_RDLGY_SRVC_CD":[753,6550,2520,2380],"DTRY_SRVC_CD":[1105,6504,2888,1706],"DCTD_ER_SRVC_CD":[3672,5127,915,2489],"ICU_SRVC_CD":[6276,5108,322,497],"NEONTL_ICU_SRVC_CD":[11053,804,54,292],"OPEN_HRT_SRGRY_SRVC_CD":[10378,1257,324,244]}
    require(set(b["fields"])==set(expected),"QIES field baseline mismatch")
    for field,counts in expected.items():
        require(b["fields"][field]["value_distribution"]=={"blank":1395,**{"code_"+str(i):v for i,v in enumerate(counts)}},"QIES distribution mismatch: "+field)
    with closing(sqlite3.connect(db_path)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        check_integrity(db)
        counts={}
        for table,key,n in (("iqies_capability_observations","iqies",68604),("qies_hospital_service_observations","qies",163176)):
            actual=db.execute("SELECT count(*) FROM "+table).fetchone()[0]
            require(actual==n,"derived count mismatch "+key);counts[key]=actual
            orphans=db.execute("SELECT count(*) FROM "+table+" o LEFT JOIN certification_records c ON c.registry=o.registry AND c.row_number=o.row_number WHERE c.row_number IS NULL").fetchone()[0]
            require(orphans==0,"orphan capability observation")
        require(db.execute("SELECT source_sha256 FROM iqies_capability_release").fetchone()[0]==db.execute("SELECT source_sha256 FROM certification_releases WHERE registry='iqies'").fetchone()[0],"iQIES release mismatch")
        require(db.execute("SELECT source_sha256 FROM qies_hospital_service_release").fetchone()[0]==db.execute("SELECT source_sha256 FROM certification_releases WHERE registry='qies'").fetchone()[0],"QIES release mismatch")
    return {"derived_observations":counts,"total_derived_observations":sum(counts.values()),"iqies_dictionary_sha256":iq.DICT_SHA,"qies_layout_sha256":q.LAYOUT_SHA,"qies_semantic_status":b["semantic_status"],"iqies_field_states":a["field_states"],"qies_field_distributions":{k:v["value_distribution"] for k,v in b["fields"].items()},"note":"Derived source-scoped observations, not additional provider records; QIES historical domain provisional. Local only."}
