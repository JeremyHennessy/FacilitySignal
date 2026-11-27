"""National HTTP qualification of the exact recovered iQIES service database.

Loopback-only, no raw or row-level output, no storage writes. Reconstruct only
the pinned iQIES source and existing private base when no sidecar is retained.
"""
import argparse
import json
import os
import tempfile
import threading
import time
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import azure_national_archive as archive
import facilitysignal as fs
import private_iqies_service_research as research
from build_combined import readonly, require, sha
from local_research import STATES
from scripts import azure_verified_extension as ext
from scripts import qualify_iqies_national_services as national
from scripts.qualify_iqies_sidecar_roundtrip import ReadOnlyStore

ROUTE = "/api/iqies-additional-services"
ROW_KEYS = {"registry", "row_number", "provider_id", "name", "city", "state",
            "field", "provider_scope", "value_state"}


@contextmanager
def server(path, enabled):
    parent = fs.handler(path, private_service_extension=enabled)

    class QuietHandler(parent):
        # Never write real query tokens or returned institutional rows to CI logs.
        def log_message(self, format, *args):
            pass

    with fs.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler) as http:
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        try:
            yield "http://127.0.0.1:" + str(http.server_port)
        finally:
            http.shutdown()
            worker.join(timeout=5)


def request(url, params, status=200):
    try:
        with urlopen(url + ROUTE + "?" + urlencode(params), timeout=30) as res:
            require(res.status == status == 200, "unexpected HTTP success")
            require(res.headers.get("Cache-Control") == "no-store"
                    and res.headers.get("X-Content-Type-Options") == "nosniff"
                    and res.headers.get_content_type() == "application/json",
                    "private response headers")
            return json.load(res)
    except HTTPError as exc:
        with exc:
            require(exc.code == status and status != 200, "unexpected HTTP rejection")
            exc.read()
        return None


def expected_page(db, field, value=None, state=None, term=None, page=1, limit=3):
    # Independent source-native SQL control, with literal substring semantics
    # rather than the route's LIKE pattern builder.
    where = ["o.registry='iqies'", "o.field=?"]
    args = [field]
    if value:
        where.append("o.value_state=?")
        args.append(value)
    if state:
        where.append("c.state=?")
        args.append(state)
    if term is not None:
        where.append("(instr(lower(c.name),lower(?))>0 OR instr(lower(c.provider_id),lower(?))>0 OR instr(lower(c.city),lower(?))>0)")
        args.extend([term]*3)
    clause = (" FROM iqies_additional_service_observations o "
              "JOIN certification_records c ON c.registry=o.registry AND c.row_number=o.row_number WHERE "
              + " AND ".join(where))
    total = db.execute("SELECT count(*)"+clause, args).fetchone()[0]
    rows = db.execute("SELECT c.registry,c.row_number,c.provider_id,c.name,c.city,c.state,"
                      "o.field,o.provider_scope,o.value_state"+clause+
                      " ORDER BY c.state,c.name COLLATE NOCASE,c.row_number LIMIT ? OFFSET ?",
                      args+[limit,(page-1)*limit])
    keys = [c[0] for c in rows.description]
    return total, [dict(zip(keys, row)) for row in rows]


def verify_response(payload, field, control, page, limit, expected):
    total, rows = control
    require(payload["status"] == "source_observations" and payload["field"] == field,
            "service response status")
    require(payload["scope"] == research.RULES[field][0] and payload["registry"] == "iqies",
            "source scope mismatch")
    require(payload["label"] == research.LABELS[field] and payload["total"] == total
            and payload["page"] == page and payload["limit"] == limit, "response metadata mismatch")
    require(payload["release"] == {"source_sha256": expected["source_sha256"],
            "dictionary_sha256": expected["dictionary_sha256"],
            "source_period": expected["source_period"],
            "source_rows": expected["verified_source_rows"]}, "response lineage mismatch")
    require(all(set(row) == ROW_KEYS for row in payload["rows"]), "unexpected response columns")
    require(payload["rows"] == rows, "response rows differ from independent control")


def qualify_http(path, expected):
    path = Path(path)
    original = sha(path)
    require(original == expected["database_sha256"], "database pin mismatch")
    checks = {"field_state": 0, "all_states": 0, "pagination": 0, "geography": 0,
              "literal_search": 0, "invalid_requests": 0, "default_denial": 0}
    elapsed = []
    with server(path, False) as url:
        request(url, {"field": next(iter(expected["field_states"]))}, 404)
        checks["default_denial"] += 1
    with closing(readonly(path)) as db, server(path, True) as url:
        def check(field, value=None, state=None, term=None, page=1, limit=3):
            params = {"field": field, "page": page, "limit": limit}
            for key, val in (("value_state", value), ("state", state), ("q", term)):
                if val is not None:
                    params[key] = val
            control = expected_page(db, field, value, state, term, page, limit)
            start = time.monotonic()
            payload = request(url, params)
            elapsed.append(time.monotonic()-start)
            verify_response(payload, field, control, page, limit, expected)
            return control

        for field, states in expected["field_states"].items():
            total, sample = check(field)
            require(total == sum(states.values()), "field total differs from pinned counts")
            checks["all_states"] += 1
            for value, count in states.items():
                observed, _ = check(field, value=value)
                require(observed == count, "state total differs from pinned counts")
                checks["field_state"] += 1
            if total > 3:
                check(field, page=2)
                checks["pagination"] += 1
            # Select a jurisdiction that is actually represented for this field.
            available = next((row["state"] for row in sample if row["state"] in STATES), None)
            if available:
                check(field, state=available)
                checks["geography"] += 1
            term = next((row["provider_id"] for row in sample
                         if row["provider_id"] and len(row["provider_id"]) <= 120
                         and row["provider_id"].isascii()), None)
            if term:
                check(field, term=term)
                checks["literal_search"] += 1

        field = next(iter(expected["field_states"]))
        # Literal wildcard characters must not expand to the whole data set.
        for term in ("%", "_", "' OR 1=1 --"):
            check(field, term=term)
            checks["literal_search"] += 1
        for bad in ({"field": "unsupported"}, {"field": field, "value_state": "invalid"},
                    {"field": field, "state": "XX"}, {"field": field, "limit": "101"},
                    {"field": field, "page": "0"}, {"field": field, "min": "1"},
                    {"field": field, "q": "x"*121}):
            request(url, bad, 400)
            checks["invalid_requests"] += 1
    require(sha(path) == original, "API mutated qualified database")
    require(checks["field_state"] == sum(map(len, expected["field_states"].values())),
            "incomplete state tests")
    return {"checks": checks, "successful_requests": len(elapsed),
            "max_successful_request_ms": round(max(elapsed)*1000, 2),
            "database_unchanged": True, "loopback_only": True,
            "response_rows_published": 0}


def run(store, root):
    expected = research.pinned()
    before = ext.national_manifest(store)
    require(before["receipt_sha256"] == expected["base_receipt_sha256"],
            "base receipt changed")
    rebuilt = national.run(store, root)
    require(rebuilt == expected, "reconstruction differs from pinned receipt")
    candidate = root / "candidate" / "facilitysignal.sqlite3"
    result = qualify_http(candidate, expected)
    ext.unchanged(store, before)
    return {**result, "format_version": 1, "database_sha256": sha(candidate),
            "base_release": expected["base_release"], "source_records": expected["baseline_source_records"],
            "service_observations": expected["observations"], "service_fields": len(expected["field_states"]),
            "national_pointer_unchanged": True, "private_storage_written": False,
            "public_promotion": False, "scope": "Temporary national loopback HTTP qualification; not production deployment or load testing."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    require(not args.receipt.exists(), "receipt exists")
    archive.run_key(os.environ)
    store = archive.Azure(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="iqies-private-api-", dir=os.environ.get("RUNNER_TEMP")) as tmp:
            result = run(ReadOnlyStore(store), Path(tmp))
    finally:
        store.close()
    with args.receipt.open("xb") as out:
        out.write(archive.encode(result))
    print("IQIES_NATIONAL_PRIVATE_HTTP", json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
