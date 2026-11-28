"""Reconcile parent-reference field availability from pinned aggregate receipts.

This does not access raw files, infer current operation, or qualify individual IRF
relationships. Historical dictionary descriptions are not current domain proof.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS = {
    "qies_raw_field_profile_20261126.json": "0dbacbc2732491559cca82dc3422b7237cb0307b",
    "qies_historical_dictionary_crosswalk_20261126.json": "d3ba3da2c42af3ead3cf573ebd3016b8972a7d84",
    "pecos_raw_field_profiles_20261126.json": "971c37613bcf823fbdebae68c20fad7941e03764",
    "pecos_field_semantic_crosswalk_20261126.json": "dbe7a6354926cd27e67145d3d596164ef03708a0",
}
QIES_FIELDS = ("PARENT_PROVIDER_NUMBER", "CAH_REHAB_DPU_SW",
               "TOT_OFSITE_REHAB_UNIT_CNT", "REHAB_UNIT_BED_CNT",
               "REHAB_UNIT_EFCTV_DT", "REHAB_UNIT_SW",
               "REHAB_UNIT_TRMNTN_CD", "REHAB_UNIT_TRMNTN_DT")


def load(name):
    raw = (ROOT / "research" / name).read_bytes()
    if hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() != PINS[name]:
        raise ValueError("aggregate evidence blob mismatch")
    return json.loads(raw)


def unique(rows, key, value):
    matches = [row for row in rows if row[key] == value]
    if len(matches) != 1:
        raise ValueError("ambiguous aggregate field or source")
    return matches[0]


def reconcile(profile, total):
    states = profile["states"]
    if any(type(v) is not int or v < 0 for v in states.values()) or sum(states.values()) != total:
        raise ValueError("field counts do not reconcile")
    return {"blank": states.get("blank", 0), "other_states": total - states.get("blank", 0)}


def audit():
    qp, qd, pp, pd = [load(name) for name in PINS]
    if qp["source_sha256"] != qd["source_sha256"] or qp["rows"] != 13598:
        raise ValueError("QIES source scope mismatch")
    h = unique(pp["sources"], "source", "hospital-enrollment")
    hd = unique(pd["sources"], "source", "hospital-enrollment")
    if h["source_sha256"] != hd["source_sha256"] or h["profiled_rows"] != 9120:
        raise ValueError("PECOS source scope mismatch")
    result = {}
    for name in QIES_FIELDS:
        f = unique(qp["fields"], "field", name)
        d = unique(qd["fields"], "field", name)
        if f["ordinal"] != d["ordinal"] or d["distinct_candidate_definitions"] != 1:
            raise ValueError("field crosswalk mismatch")
        result[name] = {**reconcile(f, qp["rows"]), "ordinal": f["ordinal"],
                        "historical_category_scopes": sorted({x[0] for y in d["definitions"] for x in y["locations"]})}
    p = unique(h["fields"], "field", "CAH OR HOSPITAL CCN")
    d = unique(hd["fields"], "field", p["field"])
    if p["ordinal"] != d["ordinal"] or "rural emergency hospital" not in d["meaning"].lower():
        raise ValueError("PECOS reference semantics not corroborated")
    if result["PARENT_PROVIDER_NUMBER"]["other_states"] != 0:
        raise ValueError("parent availability changed; review required")
    return {
        "status": "aggregate_reference_availability_verified",
        "qies_rows": qp["rows"], "qies_source_sha256": qp["source_sha256"],
        "qies_fields": result, "pecos_hospital_enrollment_rows": h["profiled_rows"],
        "pecos_source_sha256": h["source_sha256"],
        "pecos_reh_predecessor_reference": {**reconcile(p, h["profiled_rows"]),
                                            "ordinal": p["ordinal"], "meaning": d["meaning"]},
        "confirmed_irf_parent_links": 0, "new_retained_rows": 0,
        "publisher_downloads": 0, "azure_calls": 0,
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
