"""FacilitySignal development alpha. Local, read-only browser; explicit offline imports."""
import argparse
import csv
import hashlib
import html
import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "facilitysignal.sqlite3"
STATES = "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR VI".split()
CATALOG = {
    "hospital": ("xubh-q36u", "Hospital", "FS-006"),
    "nursing": ("4pq5-n9py", "Nursing home", "FS-038"),
    "dialysis": ("23ew-n7w9", "Dialysis", "new adapter; original register unchanged"),
    "nursing-health": ("r5ix-sfxw", "Nursing home health citations", "FS-033"),
    "nursing-fire": ("ifjz-ge4w", "Nursing home fire safety citations", "CMS Provider Data Catalog"),
    "home-health": ("6jpm-sxkc", "Home health agency", "CMS Provider Data Catalog"),
    "hospice": ("yc9t-dgbk", "Hospice", "CMS Provider Data Catalog"),
    "rehabilitation": ("7t8x-u3ir", "Inpatient rehabilitation facility", "CMS Provider Data Catalog"),
    "long-term-hospital": ("azum-44iv", "Long-term care hospital", "CMS Provider Data Catalog"),
}
REGISTER = ROOT / "research" / "facilitysignal_source_register_v0.2.json"
COVERAGE = ROOT / "research" / "coverage_status.json"
FINDING_DATASETS = {"nursing-health", "nursing-fire"}
FACILITY_DATASETS = set(CATALOG) - FINDING_DATASETS

def source_url(dataset):
    return "https://data.cms.gov/provider-data/dataset/" + CATALOG[dataset][0]

def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as db:
        db.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))

def clean_key(key):
    return re.sub("[^a-z0-9]", "", key.lower())

def value(row, *keys, required=False):
    for key in keys:
        v = row.get(clean_key(key), "")
        if v:
            return v
    if required:
        raise ValueError("missing required field: " + keys[0])
    return ""

def ccn(row):
    result = value(row, "CMS Certification Number (CCN)", "Facility ID", required=True).upper()
    if not re.fullmatch("[A-Z0-9]{6}", result):
        raise ValueError("invalid CCN (retain leading zeros): " + result)
    return result

def state(row):
    result = value(row, "State", required=True).upper()
    if result not in STATES:
        raise ValueError("unrecognized jurisdiction: " + result)
    return result

def normalize_facility(dataset, row):
    return (
        dataset, ccn(row), value(row, "Facility Name", "Provider Name", "Provider", required=True),
        " ".join(filter(None, [value(row, "Address", "Provider Address", "Address Line 1", "Street Address"), value(row, "Address Line 2")])),
        value(row, "City/Town", "City", required=True), state(row),
        value(row, "ZIP Code"), value(row, "County/Parish", "CountyName", "County"),
        CATALOG[dataset][1], value(row, "Hospital Type", "Provider Type"),
        value(row, "Hospital Ownership", "Ownership Type", "Profit or Non-Profit", "Ownership"),
        value(row, "Chain Name", "Chain Organization"),
        value(row, "Number of Certified Beds", "# of Dialysis Stations", "Number of Dialysis Stations"),
    )

def normalize_finding(dataset, row):
    # Hash all normalized source columns, not a guessed unique survey key.
    digest = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    survey = value(row, "Survey Date", required=True)
    try:
        survey = date.fromisoformat(survey).isoformat()
    except ValueError:
        survey = datetime.strptime(survey, "%m/%d/%Y").date().isoformat()
    return (
        dataset, digest, ccn(row), value(row, "Provider Name", required=True),
        state(row), survey, value(row, "Survey Type"),
        value(row, "Deficiency Prefix") + value(row, "Deficiency Tag Number", required=True),
        value(row, "Deficiency Category"), value(row, "Deficiency Description", required=True),
        value(row, "Scope Severity Code"), value(row, "Deficiency Corrected"),
        value(row, "Correction Date"),
    )

def import_csv(path, dataset, csv_path, release, expected_rows):
    if dataset not in CATALOG:
        raise ValueError("unsupported dataset")
    if date.fromisoformat(release).isoformat() != release or date.fromisoformat(release) > date.today():
        raise ValueError("invalid release date")
    if expected_rows < 1:
        raise ValueError("expected-rows must be positive")
    csv_path = Path(csv_path)
    # Read immutable input bytes once for consistent hash + parse.
    # Current four CSVs fit development memory; large NPPES needs streaming staging.
    raw = csv_path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    import io
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    if not reader.fieldnames:
        raise ValueError("missing CSV header")
    keys = [clean_key(k) for k in reader.fieldnames]
    if len(set(keys)) != len(keys):
        raise ValueError("ambiguous normalized headers")
    finding = dataset in FINDING_DATASETS
    table = "findings" if finding else "facilities"
    init(path)
    with closing(connect(path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        latest = db.execute("SELECT r.published_on,r.sha256,r.input_rows FROM current_release c JOIN releases r ON r.id=c.release_id WHERE c.dataset=?", (dataset,)).fetchone()
        if latest and release < latest["published_on"]:
            raise ValueError("older release cannot replace current snapshot")
        if latest and release == latest["published_on"] and checksum == latest["sha256"]:
            if expected_rows != latest["input_rows"]:
                raise ValueError("declared count differs from existing release")
            return {"status":"unchanged", "dataset":dataset, "input_rows":expected_rows}
        if latest and release == latest["published_on"]:
            raise ValueError("same release date with changed bytes; review source revision before replacing")
        run = db.execute("INSERT INTO releases(dataset,published_on,imported_at,sha256,input_rows,stored_rows,duplicate_rows,source_url) VALUES(?,?,?,?,0,0,0,?)",
                         (dataset,release,datetime.now(timezone.utc).isoformat(),checksum,source_url(dataset))).lastrowid
        db.execute("DELETE FROM " + table + " WHERE dataset=?", (dataset,))
        count = stored = duplicates = 0
        for record in reader:
            count += 1
            if None in record or any(v is None for v in record.values()):
                raise ValueError("malformed CSV row " + str(count))
            row = {clean_key(k): v.strip() for k,v in record.items()}
            normalized = normalize_finding(dataset,row) if finding else normalize_facility(dataset,row)
            args = normalized + (run,)
            sql = "INSERT INTO " + table + " VALUES(" + ",".join("?" for _ in args) + ")"
            if finding:
                sql += " ON CONFLICT(dataset,row_hash) DO NOTHING"
            result = db.execute(sql,args)
            stored += result.rowcount
            duplicates += 1-result.rowcount
        if count != expected_rows or stored < 1:
            raise ValueError("snapshot count mismatch: received %d expected %d" % (count,expected_rows))
        db.execute("UPDATE releases SET input_rows=?,stored_rows=?,duplicate_rows=? WHERE id=?",(count,stored,duplicates,run))
        db.execute("INSERT INTO current_release VALUES(?,?) ON CONFLICT(dataset) DO UPDATE SET release_id=excluded.release_id",(dataset,run))
    return {"status":"imported","dataset":dataset,"input_rows":count,"stored_rows":stored,"duplicate_rows":duplicates,"sha256":checksum}

def rows(db, sql, args=()):
    return [dict(r) for r in db.execute(sql,args)]

def overview(db):
    releases = rows(db,"SELECT r.* FROM current_release c JOIN releases r ON r.id=c.release_id ORDER BY r.dataset")
    counts = {r["dataset"]:r["stored_rows"] for r in releases}
    return {
        "facility_records": sum(counts.get(k,0) for k in FACILITY_DATASETS) if any(k in counts for k in FACILITY_DATASETS) else None,
        "finding_records":sum(counts.get(k,0) for k in FINDING_DATASETS) if any(k in counts for k in FINDING_DATASETS) else None,
        "by_category":rows(db,"SELECT category,COUNT(*) AS records FROM facilities GROUP BY category ORDER BY category"),
        "by_state":rows(db,"SELECT state,COUNT(*) AS records FROM facilities GROUP BY state ORDER BY records DESC,state"),
        "releases":releases,
        "source_entries":len(json.loads(REGISTER.read_text(encoding="utf-8"))["sources"]),
        "coverage_note":"Current imported source records, not unique properties or nationwide inspection coverage."
    }

def page_args(params):
    try:
        page = min(100000,max(1,int(params.get("page","1"))))
        limit = min(100,max(1,int(params.get("limit","25"))))
    except ValueError:
        raise ValueError("invalid page or limit")
    return page,limit

def paged(db, kind, params):
    page,limit = page_args(params)
    where = []
    values = []
    fields = ("name","city","ccn","zip","chain") if kind == "facilities" else ("provider_name","ccn","description","tag","category")
    query = params.get("q","").strip()[:160]
    if query:
        pattern = "%" + query.replace("\\","\\\\").replace("%","\\%").replace("_","\\_") + "%"
        where.append("("+" OR ".join(f+" LIKE ? ESCAPE '\\'" for f in fields)+")")
        values.extend([pattern]*len(fields))
    for key,col in (("state","state"),("dataset","dataset"),("ccn","ccn")):
        if params.get(key):
            where.append(col+"=?")
            values.append(params[key])
    clause = " WHERE "+" AND ".join(where) if where else ""
    total = db.execute("SELECT count(*) FROM "+kind+clause,values).fetchone()[0]
    order = "name COLLATE NOCASE,dataset,ccn" if kind=="facilities" else "survey_date DESC,ccn,row_hash"
    result = rows(db,"SELECT * FROM "+kind+clause+" ORDER BY "+order+" LIMIT ? OFFSET ?", values+[limit,(page-1)*limit])
    return {"rows":result,"total":total,"page":page,"limit":limit}

def sources(params):
    data = json.loads(REGISTER.read_text(encoding="utf-8"))["sources"]
    coverage = {x["id"]:x for x in json.loads(COVERAGE.read_text(encoding="utf-8"))["sources"]} if COVERAGE.exists() else {}
    data = [{**s,"qualification_status":coverage.get(s["id"],{}).get("status","discovered_not_tested")} for s in data]
    q = params.get("q","").lower().strip()[:160]
    for k in ("category","priority","jurisdiction"):
        if params.get(k):
            data = [s for s in data if s.get(k)==params[k]]
    if q:
        data = [s for s in data if q in json.dumps(s,ensure_ascii=False).lower()]
    p,l = page_args(params)
    return {"rows":data[(p-1)*l:p*l],"total":len(data),"page":p,"limit":l}

def esc(v):
    return html.escape(str(v if v is not None else "—"),quote=True)

def link(path, params=None):
    return esc(path+("?" + urlencode(params) if params else ""))

def fmt(v):
    return "—" if v is None else f"{v:,}" if isinstance(v,int) else esc(v)

def table(headers, body):
    if not body:
        return '<div class="empty">No matching records in the currently imported data. This is not evidence of compliance or absence.</div>'
    return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+x+'</td>' for x in r)+'</tr>' for r in body)+'</tbody></table></div>'

def layout(title, path, body):
    nav = [("/","Overview"),("/facilities","Facilities"),("/findings","Inspections"),("/hospital-surveys","Hospital surveys"),("/certifications","Certifications"),("/sources","Data sources")]
    links = "".join('<a href="'+p+'"'+(' aria-current="page"' if path==p else '')+'>'+t+'</a>' for p,t in nav)
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+esc(title)+' | FacilitySignal</title><link rel="stylesheet" href="/styles.css"></head><body><aside><a class="brand" href="/">Facility<span>Signal</span><small>PHARM3R</small></a><div class="nav-label">NATIONAL INTELLIGENCE</div><nav>'+links+'</nav><div class="aside-foot">Development alpha<br>United States · local data</div></aside><main><header><span>Healthcare facility intelligence</span><span class="status">LOCAL WORKSPACE</span></header><section class="content"><h1>'+esc(title)+'</h1>'+body+'</section><footer>Source-backed intelligence · Missing records do not establish compliance.</footer></main></body></html>'

def select(name, label, options, params):
    return '<label>'+esc(label)+'<select name="'+esc(name)+'"><option value="">All</option>'+''.join('<option value="'+esc(v)+'"'+(' selected' if params.get(name)==v else '')+'>'+esc(t)+'</option>' for v,t in options)+'</select></label>'

def filters(params, kind):
    controls = '<label>Search<input name="q" value="'+esc(params.get("q",""))+'" placeholder="Name, CCN, keyword"></label>'
    if kind=="sources":
        controls += select("priority","Priority",[(x,x) for x in ("P0","P1","P2")],params)
        controls += select("jurisdiction","Jurisdiction",[(x,x) for x in ["US"]+STATES],params)
    else:
        controls += select("state","State / territory",[(s,s) for s in STATES],params)
        if kind=="facilities":
            controls += select("dataset","Facility type",[(k,v[1]) for k,v in CATALOG.items() if k in FACILITY_DATASETS],params)
        else:
            controls += select("dataset","Citation source",[(k,v[1]) for k,v in CATALOG.items() if k in FINDING_DATASETS],params)
    return '<form class="filters" method="get">'+controls+'<button>Search</button><a href="'+('/sources' if kind=="sources" else '/'+kind)+'">Reset</a></form>'

def pager(path, params, result):
    p,l,n = result["page"],result["limit"],result["total"]
    parts = ['<span>'+fmt(n)+' matching records · page '+fmt(p)+'</span>']
    if p>1:
        parts.append('<a href="'+link(path,{**params,"page":p-1})+'">Previous</a>')
    if p*l<n:
        parts.append('<a href="'+link(path,{**params,"page":p+1})+'">Next</a>')
    return '<div class="pagination">'+"".join(parts)+'</div>'

def source_anchor(url):
    return '<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">Official source</a>' if url.startswith("https://") else esc(url)

def render_overview(db):
    d = overview(db)
    cards = [("Facility records",d["facility_records"],"Imported provider records"),("Jurisdictions represented",len(d["by_state"]) if d["facility_records"] is not None else None,"Based on imported addresses"),("Health & fire citations",d["finding_records"],"Nursing home records only"),("Discovered sources",d["source_entries"],"Research inventory, not live feeds")]
    body = '<p class="intro">National directory, compliance and infrastructure intelligence. Coverage increases as validated snapshots are imported.</p><div class="metrics">'+''.join('<article><small>'+esc(a)+'</small><strong>'+fmt(b)+'</strong><span>'+esc(c)+'</span></article>' for a,b,c in cards)+'</div>'
    body += '<h2>Current source releases</h2>'+table(["Dataset","Published","Imported","Rows"],[[esc(CATALOG[r["dataset"]][1]),esc(r["published_on"]),esc(r["imported_at"][:10]),fmt(r["stored_rows"])] for r in d["releases"]])
    body += '<div class="columns"><section><h2>By provider type</h2>'+table(["Type","Records"],[[esc(r["category"]),fmt(r["records"])] for r in d["by_category"]])+'</section><section><h2>Geographic coverage</h2>'+table(["Jurisdiction","Records"],[[esc(r["state"]),fmt(r["records"])] for r in d["by_state"]])+'</section></div>'
    body += '<h2>Next intelligence layers</h2><div class="roadmap">Water and environmental · Equipment · Ownership · Property · Procurement<br><small>Not yet integrated. Hospital survey source coverage is shown on its own page. No service opportunity scores are published.</small></div>'
    return layout("National overview","/",body)

def render_list(db, kind, params):
    result = sources(params) if kind=="sources" else paged(db,kind,params)
    body = filters(params,kind)
    if kind=="facilities":
        headers = ["Facility / CCN","Type","Location","Ownership / chain","Source"]
        data = [[ '<a class="record" href="'+link("/facility",{"dataset":r["dataset"],"ccn":r["ccn"]})+'">'+esc(r["name"])+'</a><small>'+esc(r["ccn"])+'</small>',esc(r["category"]),esc(r["city"]+", "+r["state"]+" "+r["zip"]),esc(r["ownership"] or "Unknown")+'<small>'+esc(r["chain"])+'</small>',source_anchor(source_url(r["dataset"]))] for r in result["rows"]]
        title="Facilities"
    elif kind=="findings":
        headers=["Provider / CCN","Survey date","Tag / severity","Finding","Correction status"]
        data=[[ '<a href="'+link("/facility",{"dataset":"nursing","ccn":r["ccn"]})+'">'+esc(r["provider_name"])+'</a><small>'+esc(r["ccn"]+" · "+r["state"])+'</small>',esc(r["survey_date"]),esc(r["tag"]+" / "+r["severity"])+"<small>"+esc(CATALOG[r["dataset"]][1])+"</small>",esc(r["description"]),esc(r["correction_status"] or "Unknown")+'<small>'+esc(r["correction_date"])+'</small>'] for r in result["rows"]]
        title="Inspections and compliance"
        body='<p class="intro">Current scope: CMS nursing home health and fire safety citations. Source statuses and historical records are retained; a citation is not automatically an active service need.</p>'+body
    else:
        headers=["Source","Jurisdiction","Priority","Discovery status","Ingestion / reuse"]
        data=[[esc(r["id"]+" · "+r["source"])+'<small>'+esc(r["publisher"])+' · '+source_anchor(r["source_url"])+'</small>',esc(r["jurisdiction"]),esc(r["priority"]),esc(r["discovery_status"]),esc(r["qualification_status"])+'<small>'+esc(r["reuse_review"])+'</small>'] for r in result["rows"]]
        title="Data source register"
        body='<p class="intro">Original research inventory with a separate qualification ledger. Historical qualification is not proof that the source is present in this local database.</p>'+body
    return layout(title,"/"+kind,body+table(headers,data)+pager("/"+kind,params,result))

def render_detail(db,params):
    dataset, ident = params.get("dataset",""),params.get("ccn","")
    r = db.execute("SELECT f.*,r.published_on,r.source_url FROM facilities f JOIN releases r ON r.id=f.release_id WHERE f.dataset=? AND f.ccn=?",(dataset,ident)).fetchone()
    if not r:
        return None
    body = '<p class="intro">'+esc(r["category"]+" · CCN "+r["ccn"]+" · "+r["city"]+", "+r["state"])+'</p><div class="details">'
    labels = [("Address",r["address"]+" "+r["city"]+" "+r["state"]+" "+r["zip"]),("Subtype",r["subtype"]),("Reported ownership",r["ownership"]),("Reported chain",r["chain"]),("Certified beds" if dataset=="nursing" else "Dialysis stations" if dataset=="dialysis" else "Capacity",r["capacity"]),("Source release",r["published_on"])]
    body += ''.join('<article><small>'+esc(k)+'</small><strong>'+esc(v or "Not reported")+'</strong></article>' for k,v in labels)+'</div><p>'+source_anchor(r["source_url"])+'</p>'
    if dataset=="nursing":
        result=paged(db,"findings",{"ccn":ident,"limit":"25"})
        body += '<h2>Health and fire safety citations · '+fmt(result["total"])+' matching imported records</h2><p>Exact CCN linkage within the nursing home source scope. A missing citation does not indicate compliance.</p>'+table(["Date","Tag","Description","Correction status"],[[esc(x["survey_date"]),esc(x["tag"]),esc(x["description"]),esc(x["correction_status"] or "Unknown")] for x in result["rows"]])+'<p><a href="'+link("/findings",{"ccn":ident})+'">View all matching citations</a></p>'
    if dataset in ("hospital","rehabilitation","long-term-hospital"):
        survey=hospital_survey_search(db,{"ccn":ident,"limit":"5"})
        if survey["release"]:
            body += '<h2>Hospital survey evidence</h2><p>'+fmt(survey["total"])+' matching source rows by exact CCN; not a resolved physical-site relationship or current open deficiency count. <a href="'+link("/hospital-surveys",{"ccn":ident})+'">View source records</a></p>'
        else:
            body += '<h2>Hospital surveys</h2><p>QCOR source not loaded into this local snapshot.</p>'
    body += '<h2>Additional intelligence</h2><div class="roadmap">Water, equipment, property, ownership relationships and contracts have not been integrated. Unknown is not zero.</div>'
    return layout(r["name"],"/facilities",body)

def registry_search(db, params):
    p,l=page_args(params)
    clauses,values=[],[]
    for k in ("registry","state"):
        if params.get(k):
            clauses.append(k+"=?")
            values.append(params[k])
    q=params.get("q","").strip()[:160]
    if q:
        pattern="%"+q.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
        clauses.append("(provider_id LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\' OR city LIKE ? ESCAPE '\\' OR address LIKE ? ESCAPE '\\')")
        values.extend([pattern]*4)
    where=" WHERE "+" AND ".join(clauses) if clauses else ""
    n=db.execute("SELECT count(*) FROM certification_records"+where,values).fetchone()[0]
    data=rows(db,"SELECT * FROM certification_records"+where+" ORDER BY name COLLATE NOCASE,registry,row_number LIMIT ? OFFSET ?",values+[l,(p-1)*l])
    releases=rows(db,"SELECT * FROM certification_releases ORDER BY registry")
    return {"rows":data,"total":n,"page":p,"limit":l,"releases":releases,"note":"Source registry records, including historical/terminated records; not unique active providers."}

def render_certifications(db,params):
    result=registry_search(db,params)
    form='<form class="filters" method="get"><label>Search<input name="q" value="'+esc(params.get("q",""))+'" placeholder="Name, provider number, city"></label>'+select("registry","Registry",[("qies","QIES"),("iqies","iQIES"),("clia","CLIA")],params)+select("state","State / territory",[(s,s) for s in STATES],params)+'<button>Search</button><a href="/certifications">Reset</a></form>'
    body='<p class="intro">CMS certification records are stored separately from Care Compare providers. Historical and terminated records are included. Status and provider-type codes are source-native; do not infer an active facility from a listed record.</p>'
    body+=table(["Registry","Release period","Source rows"],[[esc(x["registry"]),esc(x["period"]),fmt(x["row_count"])] for x in result["releases"]])+form
    body+=table(["Provider / identifier","Registry","Location","Type code","Certification / termination"],[[esc(r["name"] or "Not reported")+'<small>'+esc(r["provider_id"] or "No source ID")+'</small>',esc(r["registry"]),esc(r["address"]+" "+r["city"]+" "+r["state"]+" "+r["zip"]),esc(r["provider_type"] or "Not reported"),esc(r["certification_date"] or "Not reported")+'<small>Termination: '+esc(r["termination_date"] or "Not reported")+'</small><small>Status: '+esc(r["status"] or "Not reported")+'</small>'] for r in result["rows"]])
    return layout("CMS certifications","/certifications",body+pager("/certifications",params,result))

def hospital_survey_search(db,params):
    p,l=page_args(params)
    release=db.execute("SELECT r.* FROM qcor_hospital_current c JOIN qcor_hospital_releases r ON r.id=c.release_id").fetchone()
    if not release:
        return {"rows":[],"total":0,"page":p,"limit":l,"release":None,"note":"Source not loaded; no conclusion about compliance."}
    clauses=["release_id=?"];args=[release["id"]]
    for k in ("state","ccn","tag","row_kind"):
        if params.get(k):
            clauses.append(k+"=?");args.append(params[k])
    q=params.get("q","").strip()[:160]
    if q:
        pattern="%"+q.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
        clauses.append("(name LIKE ? ESCAPE '\\' OR ccn LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')")
        args.extend([pattern]*3)
    where=" WHERE "+" AND ".join(clauses)
    n=db.execute("SELECT count(*) FROM qcor_hospital_rows"+where,args).fetchone()[0]
    result=rows(db,"SELECT * FROM qcor_hospital_rows"+where+" ORDER BY survey_date DESC,row_ordinal LIMIT ? OFFSET ?",args+[l,(p-1)*l])
    return {"rows":result,"total":n,"page":p,"limit":l,"release":dict(release),
            "note":"QCOR source rows including memo entries and historical survey tags. Correction status is not reported; no active violation inference. Narrative omitted."}

def render_hospital_surveys(db,params):
    result=hospital_survey_search(db,params)
    body='<p class="intro">Official CMS QCOR hospital survey records. Source rows may include repeated tags and initial comments. Correction status is unknown. <a href="https://qcor.cms.gov/Hospital_2567_Reports" target="_blank" rel="noopener noreferrer">Official report</a>.</p>'
    if result["release"]:
        body+='<p>Snapshot retrieved '+esc(result["release"]["retrieved_at"][:10])+' · '+fmt(result["release"]["stored_rows"])+' source rows. Published date unavailable.</p>'
    else:
        body+='<p>QCOR source has not been loaded into this local database.</p>'
    body+='<form class="filters" method="get"><label>Search<input name="q" value="'+esc(params.get("q",""))+'" placeholder="Facility, CCN, tag description"></label><label>CCN<input name="ccn" value="'+esc(params.get("ccn",""))+'"></label><label>Tag<input name="tag" value="'+esc(params.get("tag",""))+'"></label>'+select("state","State / territory",[(x,x) for x in STATES],params)+select("row_kind","Record type",[("tag","Non-memo tag"),("memo","Memo"),("no_tag_reported","No tag reported")],params)+'<button>Search</button><a href="/hospital-surveys">Reset</a></form>'
    body+=table(["Provider / CCN","Survey / event","Tag","Description / record type","Correction"],[[esc(r["name"])+'<small>'+esc(r["ccn"]+" · "+r["city"]+", "+r["state"])+'</small>',esc(r["survey_date"])+'<small>'+esc(r["event_id"]+" · "+r["survey_type"])+'</small>',esc(r["tag"] or "Not reported"),esc(r["description"] or "Not reported")+'<small>'+esc(r["tag_type"]+" · "+r["row_kind"])+'</small>',"Unknown"] for r in result["rows"]])
    return layout("Hospital survey evidence","/hospital-surveys",body+pager("/hospital-surveys",params,result))

def handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, data, content_type):
            payload = data.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type",content_type)
            self.send_header("Content-Length",str(len(payload)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Security-Policy","default-src 'none'; style-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)
        def do_GET(self):
            parsed=urlsplit(self.path)
            path=parsed.path
            try:
                params={k:v[0] for k,v in parse_qs(parsed.query,max_num_fields=20).items()}
                if path=="/styles.css":
                    return self.send(200,(ROOT/"web"/"styles.css").read_text(encoding="utf-8"),"text/css; charset=utf-8")
                with closing(connect(db_path)) as db:
                    if path.startswith("/api/"):
                        kind=path[5:]
                        data=overview(db) if kind=="overview" else sources(params) if kind=="sources" else registry_search(db,params) if kind=="certifications" else hospital_survey_search(db,params) if kind=="hospital-surveys" else paged(db,kind,params) if kind in ("facilities","findings") else None
                        return self.send(200 if data is not None else 404,json.dumps(data if data is not None else {"error":"not found"}),"application/json; charset=utf-8")
                    if path=="/":
                        body=render_overview(db)
                    elif path in ("/facilities","/findings","/sources"):
                        body=render_list(db,path[1:],params)
                    elif path=="/certifications":
                        body=render_certifications(db,params)
                    elif path=="/hospital-surveys":
                        body=render_hospital_surveys(db,params)
                    elif path=="/facility":
                        body=render_detail(db,params)
                    else:
                        body=None
                    return self.send(200 if body else 404,body or layout("Not found",path,"<p>Record not available in the current directory.</p><a href='/facilities'>Return to facilities</a>"),"text/html; charset=utf-8")
            except ValueError:
                return self.send(400,"Invalid request","text/plain; charset=utf-8")
            except Exception:
                self.log_error("Request failed")
                return self.send(500,"Local data service error","text/plain; charset=utf-8")
    return Handler

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",type=Path,default=Path(os.environ.get("FACILITYSIGNAL_DB",DEFAULT_DB)))
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("init")
    s=sub.add_parser("serve")
    s.add_argument("--port",type=int,default=8080)
    i=sub.add_parser("import-csv")
    i.add_argument("dataset",choices=CATALOG)
    i.add_argument("csv",type=Path)
    i.add_argument("--release",required=True)
    i.add_argument("--expected-rows",type=int,required=True)
    args=p.parse_args()
    if args.cmd=="import-csv":
        try:
            print(json.dumps(import_csv(args.db,args.dataset,args.csv,args.release,args.expected_rows),indent=2))
        except (ValueError,sqlite3.Error,OSError) as e:
            p.exit(1,"Import rejected: "+str(e)+"\n")
    else:
        init(args.db)
        if args.cmd=="serve":
            with ThreadingHTTPServer(("127.0.0.1",args.port),handler(args.db)) as server:
                print("FacilitySignal: http://127.0.0.1:"+str(server.server_port),flush=True)
                server.serve_forever()

if __name__=="__main__":
    main()
