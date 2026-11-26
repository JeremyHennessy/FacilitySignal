"""Local-only, read-only, source-scoped service and organizational research.

No data retrieval, writes, public projection, canonical site resolution, risk
ranking or purchase inference. Historical observations are not current status.
"""
import re
from iqies_capabilities import RULES
from qies_hospital_services import FIELDS
STATES=set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR VI".split())
I_STATES={"reported_count","reported_yes","reported_no","not_available","not_applicable_conflict","blank","unrecognized"}
Q_STATES={"historical_domain_code","blank","not_available","not_applicable","unrecognized"}
FAMILIES={"hospital":("hospital","rehabilitation","long-term-hospital"),"snf":("nursing",)}
def require(ok,msg):
    if not ok:raise ValueError(msg)
def exists(db,name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None
def records(cursor):
    keys=[c[0] for c in cursor.description]
    return [dict(zip(keys,r)) for r in cursor]
def one(cursor):
    result=records(cursor)
    return result[0] if result else None
def page_args(p):
    try:page,limit=int(p.get("page","1")),int(p.get("limit","25"))
    except (TypeError,ValueError):raise ValueError("Invalid pagination")
    require(1<=page<=100000 and 1<=limit<=100,"Invalid pagination")
    return page,limit
def geography(p):
    state=p.get("state","")
    require(not state or state in STATES,"Invalid state")
    return state
def pattern(q):
    require(len(q)<=120,"Search too long")
    return "%"+q.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
def bound(p,k):
    v=p.get(k,"")
    if v=="":return None
    require(re.fullmatch(r"[0-9]{1,9}",str(v)) is not None,"Invalid capacity bound")
    return int(v)
def service_search(db,p):
    registry=p.get("registry","iqies")
    field=p.get("field","oprtg_room_cnt" if registry=="iqies" else "CT_SCAN_SRVC_CD")
    state=geography(p);page,limit=page_args(p)
    q=p.get("q","").strip();value=p.get("value_state","");code=p.get("code","")
    lo,hi=bound(p,"min"),bound(p,"max")
    require(registry in ("iqies","qies"),"Unsupported registry")
    if registry=="iqies":
        require(field in RULES,"Unsupported iQIES field")
        scope,kind,label,_=RULES[field]
        valid_states=I_STATES-({"reported_yes","reported_no"} if kind=="count" else {"reported_count"})
        require(not value or value in valid_states,"Value state not applicable to field")
        require(not code,"Literal code filter applies to QIES only")
        require(kind=="count" or lo is None and hi is None,"Bounds require a count field")
        require(not value or value=="reported_count" or lo is None and hi is None,"Bounds conflict with value state")
        table="iqies_capability_observations";release_table="iqies_capability_release"
        field_expr="o.count_value AS count_value,NULL AS literal_code,o.provider_scope"
        semantics="qualified_source_specific_iqies_fields"
        release_cols="source_sha256,dictionary_sha256,source_period,dictionary_url,source_rows"
    else:
        require(field in FIELDS,"Unsupported QIES field")
        scope="Hospital category 01";label=FIELDS[field]
        require(not value or value in Q_STATES,"Invalid QIES state")
        require(not code or code in ("0","1","2","3"),"Invalid literal code")
        require(not code or not value or value=="historical_domain_code","Code conflicts with value state")
        require(lo is None and hi is None,"QIES codes are not numeric capacity")
        table="qies_hospital_service_observations";release_table="qies_hospital_service_release"
        field_expr="NULL AS count_value,o.code AS literal_code,'Hospital category 01' AS provider_scope"
        semantics="historical_2023_layout_provisional_for_2026"
        release_cols="source_sha256,layout_sha256,source_period,layout_url,layout_date,source_rows"
    require(lo is None or hi is None or lo<=hi,"Minimum exceeds maximum")
    base={"status":"not_loaded","registry":registry,"field":field,"label":label,"scope":scope,"semantic_status":semantics,"rows":[],"total":None,"page":page,"limit":limit,
          "note":"Registry observations, not unique sites, current operations, installed assets or purchasing intent. Candidate links, when present, are exact source-scoped evidence only."}
    if not exists(db,table) or not exists(db,release_table):return base
    release=one(db.execute("SELECT "+release_cols+" FROM "+release_table+" WHERE singleton=1"))
    parent=one(db.execute("SELECT source_sha256,period,row_count FROM certification_releases WHERE registry=?",(registry,)))
    if not release or not parent:return base
    if (release["source_sha256"],release["source_period"],release["source_rows"])!=(parent["source_sha256"],parent["period"],parent["row_count"]):
        return dict(base,status="lineage_mismatch")
    where=["o.registry=?","o.field=?"];args=[registry,field]
    if registry=="iqies":where.append("o.provider_scope=?");args.append(scope)
    if state:where.append("c.state=?");args.append(state)
    if q:
        like=pattern(q);where.append("(c.name LIKE ? ESCAPE '\\' OR c.provider_id LIKE ? ESCAPE '\\' OR c.city LIKE ? ESCAPE '\\')");args.extend([like]*3)
    if value:where.append("o.value_state=?");args.append(value)
    if code:where.append("o.code=?");args.append(code)
    if lo is not None:where.append("o.count_value>=?");args.append(lo)
    if hi is not None:where.append("o.count_value<=?");args.append(hi)
    clause=" FROM "+table+" o JOIN certification_records c ON c.registry=o.registry AND c.row_number=o.row_number WHERE "+" AND ".join(where)
    total=db.execute("SELECT count(*)"+clause,args).fetchone()[0]
    rows=records(db.execute("SELECT c.registry,c.row_number,c.provider_id,c.name,c.city,c.state,o.field,o.value_state,"+field_expr+clause+" ORDER BY c.state,c.name COLLATE NOCASE,c.row_number LIMIT ? OFFSET ?",args+[limit,(page-1)*limit]))
    has_candidates=exists(db,"facility_registry_candidate")
    for row in rows:
        row["provider_candidates"]=None if not has_candidates else records(db.execute("""SELECT dataset,ccn,candidate_state,address_text_agrees,city_text_agrees,zip5_agrees
          FROM facility_registry_candidate WHERE registry=? AND row_number=? AND candidate_state='same_state' ORDER BY dataset,ccn LIMIT 100""",(registry,row["row_number"])))
    return dict(base,status="source_observations",release=release,total=total,rows=rows)
def portfolio_search(db,p):
    family=p.get("family","hospital");page,limit=page_args(p);state=geography(p)
    require(family in FAMILIES,"Unsupported enrollment family")
    owner=p.get("owner_pac_id","").strip();q=p.get("q","").strip()
    require(not owner or re.fullmatch(r"[0-9]{1,10}",owner) is not None,"Invalid source organization PAC ID")
    base={"status":"not_loaded","family":family,"rows":[],"total":None,"page":page,"limit":limit,
          "note":"Organization-role source rows linked by exact source family, enrollment ID and provider PAC ID. Not unique owners, controlling interest, verified current portfolios or legal property title."}
    if not all(exists(db,x) for x in ("pecos_releases","pecos_org_role_rows","pecos_enrollment_rows")):return base
    role_source=family+"-owner";enroll_source=family+"-enrollment"
    releases=records(db.execute("SELECT source,modified,period,url,sha256 FROM pecos_releases WHERE source IN (?,?) ORDER BY source",(role_source,enroll_source)))
    if len(releases)!=2:return base
    where=["r.source=?","r.enrollment_id<>''","r.pac_id<>''","r.owner_pac_id<>''"];args=[role_source]
    if owner:where.append("r.owner_pac_id=?");args.append(owner)
    if q:where.append("r.owner_name LIKE ? ESCAPE '\\'");args.append(pattern(q))
    enrollment="e.source=? AND e.enrollment_id=r.enrollment_id AND e.pac_id=r.pac_id"
    args.append(enroll_source)
    if state:enrollment+=" AND upper(trim(json_extract(e.projection,'$.STATE')))=?";args.append(state)
    where.append("EXISTS (SELECT 1 FROM pecos_enrollment_rows e WHERE "+enrollment+")")
    clause=" FROM pecos_org_role_rows r WHERE "+" AND ".join(where)
    total=db.execute("SELECT count(*)"+clause,args).fetchone()[0]
    rows=records(db.execute("SELECT r.source,r.ordinal,r.owner_pac_id,r.owner_name,r.enrollment_id,r.pac_id,r.role_code,r.role_text"+clause+" ORDER BY r.owner_name COLLATE NOCASE,r.owner_pac_id,r.ordinal LIMIT ? OFFSET ?",args+[limit,(page-1)*limit]))
    for row in rows:
        # Do not multiply source role counts through a many-to-many enrollment join.
        args2=[enroll_source,row["enrollment_id"],row["pac_id"]]
        query="""SELECT e.ordinal,e.ccn,e.organization_name,upper(trim(json_extract(e.projection,'$.STATE'))) AS reported_state
          FROM pecos_enrollment_rows e WHERE e.source=? AND e.enrollment_id=? AND e.pac_id=?"""
        if state:query+=" AND upper(trim(json_extract(e.projection,'$.STATE')))=?";args2.append(state)
        n=db.execute("SELECT count(*) FROM ("+query+")",args2).fetchone()[0]
        candidates=records(db.execute(query+" ORDER BY e.ordinal LIMIT 25",args2))
        for entry in candidates:
            placeholders=",".join("?" for _ in FAMILIES[family])
            entry["provider_candidates"]=records(db.execute("SELECT dataset,ccn,name,state FROM facilities WHERE dataset IN ("+placeholders+") AND ccn=? AND state=? ORDER BY dataset",[*FAMILIES[family],entry["ccn"],entry["reported_state"]])) if entry["reported_state"] in STATES and re.fullmatch(r"[A-Z0-9]{6}",entry["ccn"] or "") else []
        row["enrollment_candidate_count"]=n;row["enrollment_candidates"]=candidates
    return dict(base,status="source_role_observations",releases=releases,total=total,rows=rows)
