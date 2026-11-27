"""Read-only, aggregate-only audit of the pinned National PECOS projection."""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

from ownership_evidence import FAMILY, _report_month

DB_BYTES=906149888
DB_SHA="138ad57c3719fe63895eeaff702c04b51107fe1cf6dc4daf403a554985a1f033"
PINNED_TOTALS={"hospital":{"enrollments":9120,"roles":22735},"snf":{"enrollments":14401,"roles":100231}}
CATEGORIES=("same_state_provider_candidate","ambiguous_provider_evidence","missing_enrollment_pair",
            "invalid_or_missing_provider_identity","no_directory_candidate","directory_state_conflict")


def fingerprint(p):
    h=sha256()
    n=0
    with p.open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            n+=len(block)
            h.update(block)
    return n,h.hexdigest()


def _state(value):
    return value.strip().upper() if isinstance(value,str) else ""


def _provider_valid(ccn,state):
    return bool(re.fullmatch(r"[A-Z0-9]{6}",ccn or "") and re.fullmatch(r"[A-Z]{2}",state))


def audit(db,expected=PINNED_TOTALS):
    directory=defaultdict(set)
    placeholders=','.join('?' for _ in FAMILY)
    for dataset,ccn,state in db.execute("SELECT dataset,ccn,state FROM facilities WHERE dataset IN ("+placeholders+")",tuple(FAMILY)):
        if _provider_valid(ccn,_state(state)):
            directory[(FAMILY[dataset],ccn)].add(_state(state))
    result={}
    for family in ("hospital","snf"):
        enrollment,owner=(family+"-enrollment",family+"-owner")
        periods={k:_report_month(v) for k,v in db.execute(
            "SELECT source,period FROM pecos_releases WHERE source IN (?,?)",(enrollment,owner))}
        if len(periods)!=2 or not periods.get(enrollment) or periods[enrollment]!=periods.get(owner):
            raise ValueError("pinned enrollment and organization release months do not agree")
        keys=defaultdict(set)
        enroll_count=0
        for e,p,c,s in db.execute("""SELECT enrollment_id,pac_id,ccn,json_extract(projection,'$.STATE')
                                      FROM pecos_enrollment_rows WHERE source=?""",(enrollment,)):
            enroll_count+=1
            if e and p:
                keys[e,p].add((c,_state(s)))
        counters=Counter()
        for e,p in db.execute("SELECT enrollment_id,pac_id FROM pecos_org_role_rows WHERE source=?",(owner,)):
            identities=keys.get((e,p),()) if e and p else ()
            if not identities: status="missing_enrollment_pair"
            elif len(identities)>1: status="ambiguous_provider_evidence"
            else:
                c,s=next(iter(identities))
                if not _provider_valid(c,s): status="invalid_or_missing_provider_identity"
                else:
                    known=directory[(family,c)]
                    if not known: status="no_directory_candidate"
                    elif known != {s}: status="directory_state_conflict"
                    else: status="same_state_provider_candidate"
            counters[status]+=1
        actual={"enrollments":enroll_count,"roles":sum(counters.values())}
        if actual!=expected[family]:
            raise ValueError("pinned PECOS table counts do not match")
        result[family]={"report_month":periods[enrollment],"source_rows":actual,
                        "role_dispositions":{x:counters[x] for x in CATEGORIES}}
    return result


def replay(path,size=DB_BYTES,digest=DB_SHA,expected=PINNED_TOTALS):
    path=Path(path).resolve(strict=True)
    if path.stat().st_size!=size or fingerprint(path)!=(size,digest):
        raise ValueError("not the pinned national snapshot")
    uri=path.as_uri()+"?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri,uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        rows=audit(db,expected)
    if fingerprint(path)!=(size,digest):
        raise ValueError("snapshot changed during replay")
    return {"scope":"exact national snapshot; aggregate candidate counts only",
            "database_sha256":digest,"database_bytes":size,"read_only":True,
            "families":rows,"public_promotion":False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot")
    args=p.parse_args()
    try:
        result=replay(args.snapshot)
    except (OSError,ValueError,sqlite3.Error):
        # Avoid logging paths, individual rows, or partial evidence.
        raise SystemExit("Pinned snapshot unavailable or rejected; no aggregate result")
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
