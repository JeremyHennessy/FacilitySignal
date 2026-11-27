"""Opt-in local-only research for the qualified additional iQIES service fields.

No published pack, current service confirmation, physical equipment inference,
or canonical site merge. Require exact round-trip database bytes at startup.
"""
import json
from pathlib import Path

from build_combined import require, sha
from iqies_additional_services import RULES
from iqies_capabilities import DICT_SHA

ROOT = Path(__file__).resolve().parent
ROUNDTRIP = ROOT / "research/iqies_sidecar_roundtrip_20261127.json"
NATIONAL = ROOT / "research/iqies_national_service_qualification_20261127.json"
LABELS = {
    "ft_srgry_sw": "Surgical Specialty: Podiatry Indicator",
    "ob_gyn_srgry_sw": "Surgical Specialty: Obstetrics / Gynecology Indicator",
    "opthmlgy_srgry_sw": "Surgical Specialty: Ophthalmologic Indicator",
    "orthpdc_srgry_sw": "Surgical Specialty: Orthopedic Indicator",
    "othr_srgry_sw": "Surgical Specialty: Other Indicator",
    "otlrynglgy_srgry_sw": "Surgical Specialty: Ear/Nose/Throat Indicator",
    "pain_srgry_sw": "Surgical Specialty: Pain Indicator",
    "plstc_srgry_sw": "Surgical Specialty: Plastic / Reconstructive",
    "incntr_nctrnl_srvc_sw": "Is New In-Center Nocturnal Hemodialysis",
    "sp_home_trng_sprt_hd_sw": "Is Current Home Hemodialysis",
    "sp_home_trng_sprt_pd_sw": "Is Current Home Peritoneal Dialysis"
}
STATES = {"reported_yes", "reported_no", "not_available"}


def pinned():
    return json.loads(NATIONAL.read_text())["receipt"]


def verify_database(path):
    proof = json.loads(ROUNDTRIP.read_text())["receipt"]
    prior = pinned()
    require(proof["extension_tables_exact_bidirectional_parity"]
            and proof["national_pointer_unchanged"]
            and proof["base_database_sha256"] == prior["base_database_sha256"]
            and proof["restored_database_sha256"] == prior["database_sha256"]
            and proof["observations"] == prior["observations"],
            "unqualified extension recovery")
    require(Path(path).is_file() and sha(path) == proof["restored_database_sha256"],
            "private extension database checksum mismatch")


def search(db, params):
    # Import here to avoid a cycle; existing research routes remain unchanged.
    from local_research import exists, geography, page_args, pattern, one, records
    field = params.get("field", "")
    require(field in RULES and field in LABELS, "Unsupported additional service field")
    require(set(params) <= {"field", "state", "q", "value_state", "page", "limit"},
            "Unsupported query parameter")
    state = geography(params)
    page, limit = page_args(params)
    value = params.get("value_state", "")
    require(not value or value in STATES, "Unsupported service state")
    q = params.get("q", "").strip()
    like = pattern(q) if q else None
    scope = RULES[field][0]
    result = {
        "status": "not_loaded", "field": field, "label": LABELS[field],
        "scope": scope, "registry": "iqies", "rows": [], "total": None,
        "page": page, "limit": limit,
        "semantic_status": "qualified_source_specific_iqies_service_indicator",
        "note": "Historical source-record observations; no current operations, installed assets, physical sites or purchasing intent implied. Private local research only.",
    }
    tables = ("certification_records", "certification_releases",
              "iqies_additional_service_release", "iqies_additional_service_observations")
    if not all(exists(db, t) for t in tables):
        return result
    expected = pinned()
    release = one(db.execute("SELECT source_sha256,dictionary_sha256,source_period,source_rows FROM iqies_additional_service_release WHERE singleton=1"))
    parent = one(db.execute("SELECT source_sha256,period,row_count FROM certification_releases WHERE registry='iqies'"))
    if not release or not parent:
        return result
    if (release != {"source_sha256": expected["source_sha256"], "dictionary_sha256": DICT_SHA,
                    "source_period": expected["source_period"], "source_rows": expected["verified_source_rows"]}
            or (parent["source_sha256"],parent["period"],parent["row_count"]) !=
               (release["source_sha256"],release["source_period"],release["source_rows"])):
        return dict(result, status="lineage_mismatch")
    # Verify the selected field's entire qualified domain before returning results.
    groups = db.execute("SELECT provider_scope,value_state,count(*) FROM iqies_additional_service_observations WHERE field=? GROUP BY provider_scope,value_state", (field,)).fetchall()
    observed = {(row[0],row[1]):row[2] for row in groups}
    if observed != {(scope,s):n for s,n in expected["field_states"][field].items() if n}:
        return dict(result, status="domain_mismatch")
    where = ["o.registry='iqies'", "o.field=?", "o.provider_scope=?"]
    args = [field, scope]
    if state:
        where.append("c.state=?"); args.append(state)
    if value:
        where.append("o.value_state=?"); args.append(value)
    if like:
        where.append("(c.name LIKE ? ESCAPE '\\' OR c.provider_id LIKE ? ESCAPE '\\' OR c.city LIKE ? ESCAPE '\\')")
        args.extend([like] * 3)
    clause = " FROM iqies_additional_service_observations o JOIN certification_records c ON c.registry=o.registry AND c.row_number=o.row_number WHERE " + " AND ".join(where)
    total = db.execute("SELECT count(*)" + clause, args).fetchone()[0]
    rows = records(db.execute("SELECT c.registry,c.row_number,c.provider_id,c.name,c.city,c.state,o.field,o.provider_scope,o.value_state" + clause + " ORDER BY c.state,c.name COLLATE NOCASE,c.row_number LIMIT ? OFFSET ?", args + [limit, (page-1)*limit]))
    return dict(result, status="source_observations", release=release, total=total, rows=rows)
