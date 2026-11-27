"""Private, source-scoped iQIES service extension; never changes the existing capability projection.

Requires the exact retained national DB, iQIES source and dictionary. No downloader,
public export, inferred purchase, current operation or physical-site merge.
"""
import argparse
import csv
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path

import openpyxl
import iqies_capabilities as cap
import collect_registry as registry
from build_combined import require, check_integrity, readonly, sha
from restore_snapshot import LOCK, load_lock, verify_raw
from probe_pos_fields import INVENTORY

ROOT = Path(__file__).resolve().parent
EVIDENCE = {
    "iqies_full_dictionary_metadata_20261126.json": "c1a7472e5af9fbfbde15ba0089125bd3667ace32",
    "iqies_raw_field_profile_20261126.json": "1e33c18d0d2934352914b740f24c6b2e28bdf33f",
    "iqies_projection_gap_domain_review_20261127.json": "a03417af5d818281af2d728acfe544a95f240d47",
}
RULES = {
    "ft_srgry_sw": ("ASC", 44),
    "ob_gyn_srgry_sw": ("ASC", 45),
    "opthmlgy_srgry_sw": ("ASC", 48),
    "orthpdc_srgry_sw": ("ASC", 49),
    "othr_srgry_sw": ("ASC", 50),
    "otlrynglgy_srgry_sw": ("ASC", 51),
    "pain_srgry_sw": ("ASC", 52),
    "plstc_srgry_sw": ("ASC", 53),
    "incntr_nctrnl_srvc_sw": ("ESRD", 134),
    "sp_home_trng_sprt_hd_sw": ("ESRD", 135),
    "sp_home_trng_sprt_pd_sw": ("ESRD", 137),
}
SOURCE_SHA = "50b3fd74d88e08d2eaaf60e11a9230175acae0045b9fe9f803b91be8b8359dd2"
DDL = """
CREATE TABLE iqies_additional_service_release (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 source_sha256 TEXT NOT NULL, dictionary_sha256 TEXT NOT NULL,
 source_period TEXT NOT NULL, source_rows INTEGER NOT NULL
);
CREATE TABLE iqies_additional_service_observations (
 registry TEXT NOT NULL CHECK(registry='iqies'),
 row_number INTEGER NOT NULL, field TEXT NOT NULL,
 provider_scope TEXT NOT NULL CHECK(provider_scope IN ('ASC','ESRD')),
 value_state TEXT NOT NULL CHECK(value_state IN ('reported_yes','reported_no','not_available')),
 PRIMARY KEY(registry,row_number,field),
 FOREIGN KEY(registry,row_number) REFERENCES certification_records(registry,row_number)
);
CREATE INDEX iqies_additional_service_field_state ON iqies_additional_service_observations(field,value_state);
"""

def evidence():
    objects = {}
    for filename, digest in EVIDENCE.items():
        data = (ROOT / "research" / filename).read_bytes()
        require(hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == digest,
                "reviewed evidence changed: " + filename)
        objects[filename] = json.loads(data)
    metadata, profile, gap = objects.values()
    require(profile["source_sha256"] == gap["source_sha256"] == SOURCE_SHA, "source release mismatch")
    require(profile["rows"] == gap["source_rows"] == 100334, "source rows mismatch")
    md = {f["field"]: f for f in metadata["fields"]}
    pf = {f["field"]: f for f in profile["fields"]}
    gf = {f["field"]: f for f in gap["fields"]}
    expected = {}
    reviewed = {}
    for field, (scope, row) in RULES.items():
        m, p, g = md[field], pf[field], gf[field]
        require(m["ordinal"] == p["ordinal"] == g["ordinal"] == row-1, "ordinal mismatch")
        require(m["match_status"] == "unique_metadata_match" and len(m["candidates"]) == 1, "dictionary ambiguity")
        d = m["candidates"][0]
        require(d["row"] == row and d["applicability"] == scope and d["publisher_header"] == field
                and d["format"] == "Yes/No/Not Applicable/Not Available" and d["definition"]
                and d["mapping_raw"] is None, "dictionary metadata mismatch")
        require(g["disposition"] == "bounded_domain_boolean" and not g["conflicting_scopes"], "field not screened")
        b = p["scope_counts"][scope]
        states = {k: b.get(k, 0) for k in ("reported_yes", "reported_no", "not_available")}
        require(sum(states.values()) == b["rows"] == b["applicable"], "scope states do not reconcile")
        require(p["states"] == {"not_applicable": profile["rows"]-b["rows"],
                "not_available": states["not_available"],
                "other_nonblank": states["reported_yes"]+states["reported_no"]}, "raw state mismatch")
        require(all(v.get("other_nonblank", 0) == 0 for k,v in p["scope_counts"].items() if k != scope),
                "out of scope populated field")
        expected[field] = states
        reviewed[field] = d
    return reviewed, expected

def classify(field, actual_scope, raw):
    scope, _ = RULES[field]
    if actual_scope != scope:
        require(raw.strip().casefold() == "not applicable", "out-of-scope value: " + field)
        return None
    state, value = cap.normalize_value(raw, "boolean")
    require(value is None and state in ("reported_yes","reported_no","not_available"),
            "unqualified in-scope state: " + field)
    return state

def dictionary_review(path, reviewed):
    # The original capability loader verifies the binary dictionary hash and M1 codes.
    _, codes, scopes = cap.load_dictionary(path)
    book = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        sheet = book["POS Data Dictionary"]
        sheet.reset_dimensions()
        seen = set()
        for n, row in enumerate(sheet.iter_rows(values_only=True), 1):
            row = tuple(row) + (None,)*max(0,6-len(row))
            if row[0] not in RULES:
                continue
            field = row[0]; d = reviewed[field]
            require(field not in seen and n == d["row"] and row[1] == d["format"]
                    and row[2] == d["label"] and row[3] == d["definition"]
                    and row[4] == d["applicability"] and row[5] == d["mapping_raw"], "dictionary row changed")
            seen.add(field)
        require(seen == set(RULES), "missing extension dictionary field")
    finally:
        book.close()
    return codes, scopes

def project(db, raw, item, dictionary_path):
    reviewed, expected = evidence()
    codes, scopes = dictionary_review(dictionary_path, reviewed)
    require(item["sha256"] == SOURCE_SHA and item["stored_rows"] == item["input_rows"] == 100334,
            "unqualified input release")
    verify_raw(raw, item)
    rel = db.execute("SELECT source_sha256,row_count,period FROM certification_releases WHERE registry='iqies'").fetchone()
    require(rel is not None and tuple(rel) == (SOURCE_SHA,100334,item["release"]), "base release mismatch")
    headers = [x["field"] for x in json.loads(INVENTORY.read_text())["registries"]["iqies"]["fields"]]
    require(not db.execute("SELECT 1 FROM sqlite_master WHERE name IN ('iqies_additional_service_release','iqies_additional_service_observations')").fetchone(), "extension already exists")
    counts = Counter()
    # DDL and inserts share the same transaction; a failure rolls back the extension.
    try:
        db.executescript("BEGIN IMMEDIATE;\n" + DDL)
        db.execute("INSERT INTO iqies_additional_service_release VALUES(1,?,?,?,?)",
                   (SOURCE_SHA,cap.DICT_SHA,item["release"],100334))
        with registry.open_csv(raw,item["metadata"]["zipped"],registry.source_encoding(raw,item["metadata"]["zipped"])) as source:
            reader = csv.DictReader(source)
            require(reader.fieldnames == headers, "source header changed")
            refs = db.execute("SELECT row_number,row_sha256,provider_id,provider_type FROM certification_records WHERE registry='iqies' ORDER BY row_number")
            batch = []
            n = 0
            for n,(row,ref) in enumerate(zip(reader,refs,strict=True),1):
                require(None not in row and all(v is not None for v in row.values()), "malformed source row")
                digest = hashlib.sha256(json.dumps(list(row.values()),ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
                require((n,digest,row["prvdr_num"].strip(),row["prvdr_type_id"].strip()) == tuple(ref),"source row lineage mismatch")
                code = cap.normalize_code(row["prvdr_type_id"])
                require(code in codes, "unknown provider type")
                scope = scopes.get(code)
                for field in RULES:
                    state = classify(field,scope,row[field])
                    if state is None:
                        continue
                    counts[field,state] += 1
                    batch.append(("iqies",n,field,scope,state))
                    if len(batch) >= 5000:
                        db.executemany("INSERT INTO iqies_additional_service_observations VALUES(?,?,?,?,?)",batch)
                        batch.clear()
            if batch:
                db.executemany("INSERT INTO iqies_additional_service_observations VALUES(?,?,?,?,?)",batch)
        require(n == 100334, "source row reconciliation")
        expected_counts = Counter({(f,s):v for f,b in expected.items() for s,v in b.items() if v})
        require(counts == expected_counts, "observed domain changed")
        stored = Counter({(f,s):v for f,s,v in db.execute("SELECT field,value_state,count(*) FROM iqies_additional_service_observations GROUP BY field,value_state")})
        require(stored == counts, "stored observation reconciliation")
        check_integrity(db)
        verify_raw(raw,item)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return {"verified_source_rows":n,"observations":sum(counts.values()),"field_states":expected,
            "source_sha256":SOURCE_SHA,"dictionary_sha256":cap.DICT_SHA,"source_period":item["release"],
            "limitations":"Private source-record service observations only. No physical asset, current operation, procurement, canonical site match or public publication implied."}

def build(base_db, raw, dictionary_path, output):
    output = output.resolve()
    require(not output.exists(), "output must be new")
    output.parent.mkdir(parents=True, exist_ok=True)
    item = next(s for s in load_lock(LOCK)["sources"] if s["family"]=="registry" and s["key"]=="iqies")
    old_hash = sha(base_db)
    with tempfile.TemporaryDirectory(prefix=".iqies-service-extension-",dir=output.parent) as tmp:
        ready = Path(tmp)/"ready"; ready.mkdir()
        dest = ready/"facilitysignal.sqlite3"
        with closing(readonly(base_db)) as src, closing(sqlite3.connect(dest)) as db:
            check_integrity(src)
            src.backup(db)
            db.execute("PRAGMA foreign_keys=ON")
            audit = project(db,raw,item,dictionary_path)
        require(sha(base_db)==old_hash,"base DB changed")
        audit.update(base_database_sha256=old_hash,database_sha256=sha(dest))
        (ready/"audit.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        os.rename(ready,output)
        return audit

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("base-db","raw","dictionary","output"):
        p.add_argument("--"+name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(a.base_db,a.raw,a.dictionary,a.output),indent=2))
