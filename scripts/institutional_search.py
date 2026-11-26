"""Search and qualify the existing immutable institutional field archive.

Local authorized workspace only. No server, Azure writes, publisher downloads,
or publication of a candidate pack. The public-candidate projection remains
scratch evidence until an independent release and browser qualification.
"""
import argparse
import json
import os
import re
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path

import azure_national_archive as archive
import institutional_observations as inst
from build_combined import require, readonly, check_integrity, sha
from scripts import audit_azure_archive_inventory as inventory
from scripts import azure_verified_extension as ext
from scripts import azure_source_archive as storage
from scripts.public_identity_candidate_audit import load as load_directories

ROOT = Path(__file__).resolve().parents[1]
QUAL = ROOT / "research/institutional_observations_qualification_20261126.json"
KEY = "institutional-field-observations"
PUBLIC_CANDIDATE = {
    "hospital": ("emergency_services",),
    "dialysis": ("chain_owned_or_managed", "late_shift", "in_center_hemodialysis", "peritoneal_dialysis", "home_hemodialysis_training"),
    "nursing": ("ownership_change_12_months",),
}
# Safety and oversight context is searchable in the authorized local workspace
# only; no facility-linked sprinkler coverage or survey-age exposure in the
# candidate for a static public commercial application.
PRIVATE_ONLY = {"nursing": ("sprinklers", "health_survey_over_two_years", "special_focus")}
STATES = frozenset("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR VI".split())
MAX_LIMIT = 100


def pinned():
    ledger = json.loads(inventory.LEDGER.read_text())
    inventory.totals(ledger)
    matches = [x for x in ledger["receipts"] if x["key"] == KEY and x["kind"] == "institutional_fields"]
    require(len(matches) == 1 and matches[0]["observations"] == 101534, "institutional archive pin")
    return matches[0]


def file_pin(pin, name):
    matches = [f for f in pin["files"] if f["path"] == name]
    require(len(matches) == 1, "missing archive file pin")
    return matches[0]


def check_file(path, pin):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == pin["bytes"] and sha(path) == pin["sha256"], "institutional archive file hash or size mismatch")


def criteria(source, filters, state=None):
    require(source in inst.RULES, "unsupported source")
    require(isinstance(filters, dict) and len(filters) <= len(inst.RULES[source]), "invalid filters")
    require(state is None or state in STATES, "invalid jurisdiction")
    for field, value in filters.items():
        require(field in inst.RULES[source] and value in inst.RULES[source][field][1].values(), "unsupported source-scoped field or value")


def search(db, source, filters, state=None, page=1, limit=25):
    criteria(source, filters, state)
    require(type(page) is int and 1 <= page <= 100000 and type(limit) is int and 1 <= limit <= MAX_LIMIT, "invalid pagination")
    clauses = ["p.source=?"]
    args = [source]
    if state:
        clauses.append("p.state=?")
        args.append(state)
    for field, value in sorted(filters.items()):
        clauses.append("EXISTS (SELECT 1 FROM candidate_observation o WHERE o.source=p.source AND o.ccn=p.ccn AND o.state=p.state AND o.field=? AND o.value_state=?)")
        args.extend((field, value))
    where = " AND ".join(clauses)
    base = " FROM candidate_provider p WHERE " + where
    total = db.execute("SELECT count(*)" + base, args).fetchone()[0]
    rows = [{"source": source, "ccn": ccn, "state": st} for ccn, st in db.execute("SELECT p.ccn,p.state" + base + " ORDER BY p.state,p.ccn LIMIT ? OFFSET ?", (*args, limit, (page-1)*limit))]
    return {"source": source, "state": state, "filters": filters, "total": total, "page": page, "limit": limit, "records": rows}


def profile(db, source, ccn, state):
    criteria(source, {}, state)
    require(state is not None and isinstance(ccn, str) and re.fullmatch(r"[A-Z0-9]{6}", ccn), "exact source CCN and state required")
    hit = db.execute("SELECT 1 FROM candidate_provider WHERE source=? AND ccn=? AND state=?", (source, ccn, state)).fetchone()
    if hit is None:
        return None
    release, source_sha, directory_sha = db.execute("SELECT release,source_sha256,directory_sha256 FROM candidate_release WHERE source=?", (source,)).fetchone()
    values = dict(db.execute("SELECT field,value_state FROM candidate_observation WHERE source=? AND ccn=? AND state=?", (source, ccn, state)))
    require(set(values) == set(inst.RULES[source]), "profile field scope mismatch")
    return {"source": source, "ccn": ccn, "state": state, "release": release, "source_sha256": source_sha, "directory_sha256": directory_sha, "observations": values}


def validate(db, prior, directories, directory_pins):
    check_integrity(db)
    releases = {s: (rel, sh, dsh, n) for s, rel, sh, dsh, n in db.execute("SELECT source,release,source_sha256,directory_sha256,provider_count FROM candidate_release")}
    require(set(releases) == set(prior["sources"]) == set(inst.RULES), "source membership mismatch")
    require(sum(len(x) for x in inst.RULES.values()) == prior["field_rules"], "rule count")
    results = {}
    public = {}
    for source, s in sorted(prior["sources"].items()):
        require(releases[source] == (s["release"], s["source_sha256"], s["public_sha256"], s["providers"]), "release pin mismatch")
        dp = directory_pins[source]
        require((dp["sha256"], dp["release"], dp["rows"]) == (s["public_sha256"], s["release"], s["providers"]), "public directory pin drift")
        expected = {(x["ccn"], x["state"]) for x in directories[source]["records"]}
        actual = set(db.execute("SELECT ccn,state FROM candidate_provider WHERE source=?", (source,)))
        require(len(expected) == len(actual) == s["providers"] and expected == actual, "source CCN/state membership mismatch")
        declared = {field: (header, meaning, json.loads(domain)) for field, header, meaning, domain in db.execute("SELECT field,raw_header,meaning,domain_json FROM candidate_field WHERE source=?", (source,))}
        require(declared == {k: (r[0], r[2], r[1]) for k, r in inst.RULES[source].items()}, "archive field rules changed")
        require(set(PUBLIC_CANDIDATE[source]) | set(PRIVATE_ONLY.get(source, ())) == set(declared) and not set(PUBLIC_CANDIDATE[source]) & set(PRIVATE_ONLY.get(source, ())), "field policy partition")
        by_state = Counter(st for _, st in expected)
        data = {key: {} for key in expected}
        for ccn, st, field, value in db.execute("SELECT ccn,state,field,value_state FROM candidate_observation WHERE source=?", (source,)):
            require((ccn, st) in data and field in declared and value in declared[field][2].values() and field not in data[(ccn, st)], "observation scope or value drift")
            data[(ccn, st)][field] = value
        require(all(set(v) == set(declared) for v in data.values()), "incomplete provider observations")
        field_results = {}
        for field in sorted(declared):
            counts = Counter(v[field] for v in data.values())
            require(dict(counts) == s["fields"][field], "prior national domain mismatch")
            for value in declared[field][2].values():
                members = {key for key,v in data.items() if v[field] == value}
                filtered = set(inst.filters(db, source, field, value))
                require(filtered == members, "single filter membership mismatch")
                require(search(db,source,{field:value})["total"] == len(members), "search national total mismatch")
                for state in by_state:
                    direct = sum(st == state for _,st in members)
                    require(search(db,source,{field:value},state)["total"] == direct, "state filter total mismatch")
            field_results[field] = {"observations": sum(counts.values()), "value_counts": dict(counts), "publication": "public_candidate_only" if field in PUBLIC_CANDIDATE[source] else "authorized_local_only"}
        # All pairwise filter intersections, independent set membership oracle.
        fields = sorted(declared)
        intersections = 0
        for i, left in enumerate(fields):
            for right in fields[i+1:]:
                for lv in declared[left][2].values():
                    for rv in declared[right][2].values():
                        want = sum(v[left] == lv and v[right] == rv for v in data.values())
                        require(search(db,source,{left:lv,right:rv})["total"] == want, "combined filter total mismatch")
                        intersections += 1
        # Validate deterministic pagination and exact-record profile against every source.
        first = search(db,source,{},page=1,limit=MAX_LIMIT)
        second = search(db,source,{},page=2,limit=MAX_LIMIT)
        all_keys = sorted(expected,key=lambda k:(k[1],k[0]))
        require([(x["ccn"],x["state"]) for x in first["records"]+second["records"]] == all_keys[:2*MAX_LIMIT], "pagination order or membership mismatch")
        for ccn, st in all_keys[:2*MAX_LIMIT]:
            require(profile(db,source,ccn,st)["observations"] == data[(ccn,st)], "profile evidence mismatch")
        public[source] = {"release": s["release"], "source_sha256": s["source_sha256"], "directory_sha256": s["public_sha256"], "fields": list(PUBLIC_CANDIDATE[source]), "records": [[ccn, st, *[data[(ccn,st)][k] for k in PUBLIC_CANDIDATE[source]]] for ccn,st in all_keys]}
        results[source] = {"provider_records":len(actual),"observations":len(actual)*len(declared),"fields":field_results,"combined_filter_checks":intersections,"state_count":len(by_state)}
    require(sum(x["provider_records"] for x in results.values()) == prior["source_records"] and sum(x["observations"] for x in results.values()) == prior["observations"], "institutional total mismatch")
    require(db.execute("SELECT count(*) FROM candidate_observation").fetchone()[0] == prior["observations"], "unexpected observation rows")
    pack = {"format_version": 1, "scope":"Candidate public CMS reported institutional flags; historical release, not live service, legal title, risk or compliance.", "sources": public}
    public_count = sum(len(x["records"])*len(x["fields"]) for x in public.values())
    require(public_count == 57476 and prior["observations"]-public_count == 44058, "candidate partition drift")
    return {"sources":results,"provider_records":prior["source_records"],"observations":prior["observations"],"field_rules":prior["field_rules"],"public_candidate_observations":public_count,"local_only_observations":prior["observations"]-public_count,"candidate_fields":sum(map(len,PUBLIC_CANDIDATE.values())),"local_only_fields":sum(map(len,PRIVATE_ONLY.values())),"canonical_merges":0},pack


def qualify(store, root, receipt_path):
    pin = pinned()
    national = ext.national_manifest(store)
    name = storage.prefix_for(pin["key"],pin["source_sha256"])+"/complete.json"
    rec, digest, head = ext.read_small(store,name)
    inventory.source_matches(rec,pin,national)
    for file in pin["files"]:
        ext.fetch_verified(store,rec["payload_prefix"]+"/"+file["path"],file,root/file["path"])
    db_path = root/"projection.sqlite3"
    check_file(db_path,file_pin(pin,"projection.sqlite3"))
    check_file(root/"audit.json",file_pin(pin,"audit.json"))
    prior = json.loads(QUAL.read_text())
    directories, directory_pins = load_directories(ROOT)
    with closing(readonly(db_path)) as db:
        result, pack = validate(db,prior,directories,directory_pins)
    # Candidate bytes are written only into private ephemeral scratch; never upload them here.
    candidate = root/"candidate.json"
    candidate.write_bytes(archive.encode(pack))
    result.update({"status":"PASS","scope":"Verified archive restore and local search qualification; no public release","archive_source_sha256":pin["source_sha256"],"archive_database_sha256":file_pin(pin,"projection.sqlite3")["sha256"],"archive_receipt_sha256":digest,"candidate_bytes":candidate.stat().st_size,"candidate_sha256":sha(candidate),"publisher_downloads":0,"azure_writes":0,"public_promotion":False})
    check_file(db_path,file_pin(pin,"projection.sqlite3"))
    require(ext.read_small(store,name,digest)[2]==head,"institutional receipt changed")
    ext.unchanged(store,national)
    with receipt_path.open("xb") as f:
        f.write(archive.encode(result))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="cmd",required=True)
    q=sub.add_parser("qualify")
    q.add_argument("--receipt",type=Path,required=True)
    for cmd in ("search","profile"):
        q=sub.add_parser(cmd)
        q.add_argument("--database",type=Path,required=True)
        q.add_argument("--source",choices=sorted(inst.RULES),required=True)
        q.add_argument("--state",required=cmd=="profile")
        if cmd=="profile":
            q.add_argument("--ccn",required=True)
        else:
            q.add_argument("--filter",action="append",default=[],metavar="FIELD=VALUE")
            q.add_argument("--page",type=int,default=1)
            q.add_argument("--limit",type=int,default=25)
    args=p.parse_args()
    if args.cmd=="qualify":
        require(not args.receipt.exists(),"receipt exists")
        archive.run_key(os.environ)
        store=inventory.ReadOnlyAzure(os.environ)
        try:
            with tempfile.TemporaryDirectory(prefix="institutional-search-private-") as tmp:
                result=qualify(store,Path(tmp),args.receipt)
        finally:
            store.close()
        print("FACILITYSIGNAL_INSTITUTIONAL_SEARCH_QUALIFIED",json.dumps(result,sort_keys=True),flush=True)
    else:
        pin=file_pin(pinned(),"projection.sqlite3")
        check_file(args.database,pin)
        with closing(readonly(args.database)) as db:
            if args.cmd=="profile":
                result=profile(db,args.source,args.ccn,args.state)
            else:
                parsed={}
                for item in args.filter:
                    field,sep,value=item.partition("=")
                    require(sep and field not in parsed,"invalid or duplicate filter")
                    parsed[field]=value
                result=search(db,args.source,parsed,args.state,args.page,args.limit)
        check_file(args.database,pin)
        print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
