"""Aggregate-only PECOS evidence for a source-scoped Care Compare facility.

An exact CCN/state agreement is a candidate, not a physical site, operator,
owner, or current legal relationship determination. Individual rows are excluded.
"""
import re

FAMILY={"hospital":"hospital","rehabilitation":"hospital","long-term-hospital":"hospital","nursing":"snf"}

def profile(db,dataset,ccn):
    if dataset not in FAMILY or not re.fullmatch(r"[A-Z0-9]{6}",ccn):
        return {"status":"unsupported_or_invalid_identifier","enrollment_rows":None,"organization_role_rows":None}
    facility=db.execute("SELECT state FROM facilities WHERE dataset=? AND ccn=?",(dataset,ccn)).fetchone()
    if not facility:
        return {"status":"facility_not_found","enrollment_rows":None,"organization_role_rows":None}
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pecos_releases'").fetchone():
        return {"status":"not_loaded","enrollment_rows":None,"organization_role_rows":None}
    family=FAMILY[dataset]; e=family+"-enrollment"; o=family+"-owner"
    release=db.execute("SELECT modified,period,url FROM pecos_releases WHERE source=?",(e,)).fetchone()
    owner=db.execute("SELECT modified,period,url FROM pecos_releases WHERE source=?",(o,)).fetchone()
    if not release or not owner:
        return {"status":"not_loaded","enrollment_rows":None,"organization_role_rows":None}
    state=facility[0].strip().upper()
    if not state:
        return {"status":"missing_facility_state","enrollment_rows":None,"organization_role_rows":None}
    clause="e.source=? AND e.ccn=? AND upper(trim(json_extract(e.projection,'$.STATE')))=?"
    args=(e,ccn,state)
    count=db.execute("SELECT count(*) FROM pecos_enrollment_rows e WHERE "+clause,args).fetchone()[0]
    all_id=db.execute("SELECT count(*) FROM pecos_enrollment_rows WHERE source=? AND ccn=?",(e,ccn)).fetchone()[0]
    role_sql="""SELECT count(*) FROM pecos_org_role_rows r WHERE r.source=? AND EXISTS
      (SELECT 1 FROM pecos_enrollment_rows e WHERE """+clause+""" AND e.enrollment_id=r.enrollment_id
      AND e.pac_id=r.pac_id AND e.enrollment_id<>'' AND e.pac_id<>'')"""
    roles=db.execute(role_sql,(o,*args)).fetchone()[0]
    return {"status":"same_state_identifier_candidate" if count else ("state_conflict_or_missing" if all_id else "no_candidate"),
            "enrollment_rows":count,"organization_role_rows":roles,"other_state_or_missing_rows":all_id-count,
            "enrollment_release":{"modified":release[0],"period":release[1],"url":release[2]},
            "organization_release":{"modified":owner[0],"period":owner[1],"url":owner[2]},
            "note":"Counts of source rows, not unique owners or sites. Exact CCN and state plus enrollment/PAC evidence only; no deed ownership, controlling interest or current relationship inferred."}
