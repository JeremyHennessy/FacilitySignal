"""Aggregate-only PECOS evidence for a source-scoped Care Compare facility.

An exact CCN/state agreement is a candidate, not a physical site, operator,
owner, or current legal relationship determination. Individual rows are excluded.
"""
import calendar
from datetime import date
import re

FAMILY={"hospital":"hospital","rehabilitation":"hospital","long-term-hospital":"hospital","nursing":"snf"}


def _report_month(period):
    """Recognize the pinned full-month scope and its exact YYYY-MM shorthand."""
    if not isinstance(period,str):
        return None
    m=re.fullmatch(r"([0-9]{4})-([0-9]{2})(?:-01/([0-9]{4}-[0-9]{2}-[0-9]{2}))?",period)
    if not m:
        return None
    year,month=map(int,m.group(1,2))
    try:
        first=date(year,month,1)
        last=date(year,month,calendar.monthrange(year,month)[1])
    except ValueError:
        return None
    return first.isoformat()[:7] if m[3] in (None,last.isoformat()) else None


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
    context={
        "status":"same_state_identifier_candidate" if count else ("state_conflict_or_missing" if all_id else "no_candidate"),
        "enrollment_rows":count,"other_state_or_missing_rows":all_id-count,
        "enrollment_release":{"modified":release[0],"period":release[1],"url":release[2]},
        "organization_release":{"modified":owner[0],"period":owner[1],"url":owner[2]},
    }
    em,om=_report_month(release[1]),_report_month(owner[1])
    if em is None or om is None or em!=om:
        return {**context,"organization_role_rows":None,"held_organization_role_rows":None,
                "organization_role_link_status":"held_period_unverified" if em is None or om is None else "held_period_mismatch",
                "note":"Organizational role linkage not evaluated: compatible source report months are not established."}
    # A repeated enrollment/PAC may be legitimate for multiple sites. It is
    # evidence of ambiguity, not permission to attach roles to each provider.
    sql="""WITH keys AS (
      SELECT DISTINCT e.enrollment_id, e.pac_id FROM pecos_enrollment_rows e WHERE """+clause+"""
      AND e.enrollment_id<>'' AND e.pac_id<>''
    ), assessed AS (
      SELECT k.*, EXISTS (
        SELECT 1 FROM pecos_enrollment_rows c
        WHERE c.source=? AND c.enrollment_id=k.enrollment_id AND c.pac_id=k.pac_id
          AND (c.ccn<>? OR coalesce(upper(trim(json_extract(c.projection,'$.STATE'))),'')<>?)
      ) AS hold FROM keys k
    )
    SELECT coalesce(sum(CASE WHEN a.hold=0 THEN 1 ELSE 0 END),0),
           coalesce(sum(CASE WHEN a.hold=1 THEN 1 ELSE 0 END),0)
    FROM assessed a JOIN pecos_org_role_rows r
      ON r.source=? AND r.enrollment_id=a.enrollment_id AND r.pac_id=a.pac_id"""
    roles,held=db.execute(sql,(*args,*args,o)).fetchone()
    return {**context,"organization_role_rows":roles,"held_organization_role_rows":held,
            "organization_role_link_status":"some_roles_held_provider_ambiguity" if held else "same_month_linkage_evaluated",
            "note":"Counts of source rows, not unique owners or sites. Exact CCN and state plus enrollment/PAC evidence only; conflicting provider keys are held. No deed ownership, controlling interest or current relationship inferred."}
