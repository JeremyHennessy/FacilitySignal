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

def ownership_releases(db):
    """Aggregate-only evidence. An absent release is not a zero-row observation."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pecos_releases'").fetchone():
        return []
    tables = {"enrollment":("pecos_enrollment_rows","enrollment"),
              "owner":("pecos_org_role_rows","organization_roles"),
              "chow":("pecos_chow_rows","ownership_changes")}
    out = []
    for r in rows(db,"SELECT source,period,modified,url,stored_rows FROM pecos_releases ORDER BY source"):
        suffix=r["source"].rsplit("-",1)[-1]
        if suffix not in tables:
            continue
        table_name,family=tables[suffix]
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table_name,)).fetchone():
            continue
        count=db.execute("SELECT count(*) FROM "+table_name+" WHERE source=?",(r["source"],)).fetchone()[0]
        out.append({"family":family,"source":r["source"],"title":"PECOS "+r["source"].replace("-"," "),
                    "period":r["period"]+" · Catalog modified "+r["modified"],"loaded_at":None,
                    "records":count,"declared":r["stored_rows"],"url":r["url"],
                    "path":"/ownership-coverage","params":{"kind":family}})
    return out

def loaded_releases(db, releases):
    out=[]
    for r in releases:
        dataset=r["dataset"]
        if dataset not in CATALOG:
            continue
        family="findings" if dataset in FINDING_DATASETS else "providers"
        table_name="findings" if family=="findings" else "facilities"
        count=db.execute("SELECT count(*) FROM "+table_name+" WHERE dataset=? AND release_id=?",(dataset,r["id"])).fetchone()[0]
        out.append({"family":family,"source":dataset,"title":CATALOG[dataset][1],"period":r["published_on"],
                    "loaded_at":r["imported_at"],"records":count,"declared":r["stored_rows"],"url":r["source_url"],
                    "path":"/"+table_name,"params":{"dataset":dataset}})
    for r in rows(db,"SELECT registry,title,period,imported_at,row_count,download_url FROM certification_releases ORDER BY registry"):
        count=db.execute("SELECT count(*) FROM certification_records WHERE registry=?",(r["registry"],)).fetchone()[0]
        out.append({"family":"certifications","source":r["registry"],"title":r["title"],"period":r["period"],
                    "loaded_at":r["imported_at"],"records":count,"declared":r["row_count"],"url":r["download_url"],
                    "path":"/certifications","params":{"registry":r["registry"]}})
    qcor=db.execute("SELECT r.* FROM qcor_hospital_current c JOIN qcor_hospital_releases r ON r.id=c.release_id").fetchone()
    if qcor:
        count=db.execute("SELECT count(*) FROM qcor_hospital_rows WHERE release_id=?",(qcor["id"],)).fetchone()[0]
        out.append({"family":"hospital_surveys","source":"qcor-hospital","title":"QCOR hospital survey workbook",
                    "period":"Publication date unavailable","loaded_at":qcor["retrieved_at"],"records":count,
                    "declared":qcor["stored_rows"],"url":"https://qcor.cms.gov/Hospital_2567_Reports",
                    "path":"/hospital-surveys","params":{}})
    return out+ownership_releases(db)

def family_count(items,family):
    matches=[r["records"] for r in items if r["family"]==family]
    return sum(matches) if matches else None

def overview(db):
    releases=rows(db,"SELECT r.* FROM current_release c JOIN releases r ON r.id=c.release_id ORDER BY r.dataset")
    loaded=loaded_releases(db,releases)
    return {
        "facility_records":family_count(loaded,"providers"),
        "finding_records":family_count(loaded,"findings"),
        "certification_records":family_count(loaded,"certifications"),
        "hospital_survey_records":family_count(loaded,"hospital_surveys"),
        "enrollment_records":family_count(loaded,"enrollment"),
        "organization_role_records":family_count(loaded,"organization_roles"),
        "ownership_change_records":family_count(loaded,"ownership_changes"),
        "by_category":rows(db,"SELECT dataset,category,COUNT(*) AS records FROM facilities GROUP BY dataset,category ORDER BY category,dataset"),
        "by_state":rows(db,"SELECT state,COUNT(*) AS records FROM facilities GROUP BY state ORDER BY records DESC,state"),
        "releases":releases,"loaded_releases":loaded,
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
    if kind not in ("facilities","findings"):
        raise ValueError("unsupported directory")
    page,limit=page_args(params)
    where,values=[],[]
    fields=("name","city","ccn","zip","chain","address","county") if kind=="facilities" else ("provider_name","ccn","description","tag","category")
    query=params.get("q","").strip()[:160]
    if query:
        pattern="%"+query.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
        where.append("("+" OR ".join(f+" LIKE ? ESCAPE '\\'" for f in fields)+")")
        values.extend([pattern]*len(fields))
    for key,col in (("state","state"),("dataset","dataset"),("ccn","ccn"),("identifier","ccn")):
        if params.get(key):
            where.append(col+"=?")
            values.append(params[key].strip().upper() if key in ("ccn","identifier") else params[key])
    if kind=="facilities" and params.get("identifier") and not params.get("dataset"):
        where.append("dataset IN (SELECT dataset FROM current_release)")
    clause=" WHERE "+" AND ".join(where) if where else ""
    total=db.execute("SELECT count(*) FROM "+kind+clause,values).fetchone()[0]
    orders={"name":"name COLLATE NOCASE,dataset,ccn","name_desc":"name COLLATE NOCASE DESC,dataset,ccn",
            "state":"state,city COLLATE NOCASE,name COLLATE NOCASE,dataset,ccn",
            "identifier":"ccn,dataset"}
    order=orders.get(params.get("sort"),orders["name"]) if kind=="facilities" else "survey_date DESC,ccn,row_hash"
    result=rows(db,"SELECT * FROM "+kind+clause+" ORDER BY "+order+" LIMIT ? OFFSET ?",values+[limit,(page-1)*limit])
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
    return '<div class="table-wrap" role="region" aria-label="Results table, scroll horizontally if needed" tabindex="0"><table><thead><tr>'+''.join('<th scope="col">'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+x+'</td>' for x in r)+'</tr>' for r in body)+'</tbody></table></div>'

def layout(title, path, body):
    groups=[("Intelligence",[("/","Overview"),("/search","Unified search"),("/facilities","Facilities"),("/certifications","Certifications")]),
            ("Compliance",[("/findings","Nursing home citations"),("/hospital-surveys","Hospital surveys")]),
            ("Data intelligence",[("/ownership-coverage","Ownership evidence coverage"),("/sources","Source register")])]
    def navlink(p,t):
        return '<a href="'+p+'"'+(' aria-current="page"' if path==p else '')+'>'+esc(t)+'</a>'
    links=''.join('<div class="nav-group"><div class="nav-label">'+esc(label)+'</div>'+''.join(navlink(p,t) for p,t in items)+'</div>' for label,items in groups)
    crumb='<nav aria-label="Breadcrumb" class="breadcrumbs"><a href="/">Intelligence</a><span aria-hidden="true">/</span><span aria-current="page">'+esc(title)+'</span></nav>' if path!="/" else ''
    search='<form class="global-search" method="get" action="/search" role="search"><label for="global-q" class="sr-only">Search facilities and certification registries</label><input id="global-q" name="q" placeholder="Facility, CCN, CLIA, address or city"><button>Search</button></form>'
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+esc(title)+' | FacilitySignal</title><link rel="stylesheet" href="/styles.css"></head><body><a class="skip-link" href="#main-content">Skip to content</a><aside><a class="brand" href="/">Facility<span>Signal</span><small>PHARM3R</small></a><nav aria-label="Primary navigation" class="primary-nav">'+links+'</nav><div class="aside-foot">United States · development workspace<br>Source-scoped intelligence</div></aside><main id="main-content"><header>'+search+'<span class="status">LOCAL SNAPSHOT · NOT PRODUCTION</span></header><section class="content">'+crumb+'<h1>'+esc(title)+'</h1>'+body+'</section><footer>Source-backed intelligence · Missing records do not establish compliance.</footer></main></body></html>'

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
            controls += '<label>Exact CCN<input name="identifier" value="'+esc(params.get("identifier",""))+'" placeholder="Six-character ID"></label>'
            controls += select("sort","Sort by",[("name","Name A–Z"),("name_desc","Name Z–A"),("state","State / city"),("identifier","CCN")],params)
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

def record_link(path,params,label,cls=""):
    return '<a'+(' class="'+esc(cls)+'"' if cls else '')+' href="'+link(path,params)+'">'+esc(label)+'</a>'

def release_table(items):
    return table(["Source / registry","Source date or period","Local import / retrieval","Loaded rows","Evidence"],[
        [record_link(r["path"],r["params"],r["title"],"record"),esc(r["period"]),esc(r["loaded_at"][:10] if r["loaded_at"] else "Not recorded"),
         fmt(r["records"])+('<small class="review">Manifest declares '+fmt(r["declared"])+'; review mismatch</small>' if r["records"]!=r["declared"] else ""),
         source_anchor(r["url"])] for r in items])

def render_overview(db):
    d=overview(db)
    cards=[("Care Compare providers",d["facility_records"],"Source-scoped provider records","/facilities",{}),
           ("Certification & laboratory records",d["certification_records"],"QIES, iQIES and CLIA; includes historical records","/certifications",{}),
           ("Nursing home citations",d["finding_records"],"Health and fire safety; not outstanding violations","/findings",{}),
           ("Hospital survey rows",d["hospital_survey_records"],"QCOR tags, memos and other source rows","/hospital-surveys",{}),
           ("PECOS enrollments",d["enrollment_records"],"Enrollment evidence, not unique physical sites","/ownership-coverage",{"kind":"enrollment"}),
           ("Organizational role rows",d["organization_role_records"],"Organizational evidence; individuals excluded","/ownership-coverage",{"kind":"organization_roles"}),
           ("Ownership change rows",d["ownership_change_records"],"Reported changes, not property title","/ownership-coverage",{"kind":"ownership_changes"}),
           ("Jurisdictions represented",len(d["by_state"]) if d["facility_records"] is not None else None,"Care Compare address coverage only","/#geography",{})]
    body='<p class="intro">Research the currently loaded national healthcare facility sources. Each count describes its own source population; these records are not additive measures of unique active facilities.</p><div class="metrics">'+''.join('<a class="metric" href="'+link(path,params)+'"><small>'+esc(title)+'</small><strong>'+fmt(value)+'</strong><span>'+esc(note)+'</span><span class="metric-action">'+("View loaded records" if value is not None else "Check source availability")+' <span aria-hidden="true">›</span></span></a>' for title,value,note,path,params in cards)+'</div>'
    body+='<div class="columns"><section><h2>Provider types</h2>'+table(["Type","Records"],[[record_link("/facilities",{"dataset":r["dataset"]},r["category"]),fmt(r["records"])] for r in d["by_category"]])+'</section><section id="geography"><h2>Geographic coverage</h2><p class="section-note">Care Compare records by reported jurisdiction; not complete regulatory or infrastructure coverage.</p>'+table(["Jurisdiction","Records"],[[record_link("/facilities",{"state":r["state"]},r["state"]),fmt(r["records"])] for r in d["by_state"]])+'</section></div>'
    body+='<h2>Loaded source releases</h2><p class="section-note">Counts are read from the local database. Historical qualification and source discovery are separate from this snapshot. A dash means no release is loaded for that family.</p>'+release_table(d["loaded_releases"])
    body+='<h2>Coverage and limitations</h2><div class="roadmap">Equipment, water and environmental, physical property and procurement intelligence are not yet integrated. No active compliance or service opportunity score is inferred. <a href="/sources">Review the source register and historical qualification ledger</a>.</div>'
    return layout("National overview","/",body)

def render_ownership_coverage(db,params):
    labels={"enrollment":"PECOS enrollment records","organization_roles":"PECOS organizational role records","ownership_changes":"PECOS ownership change records"}
    kind=params.get("kind","")
    if kind and kind not in labels:
        raise ValueError("unsupported ownership evidence family")
    data=ownership_releases(db)
    if kind:
        data=[r for r in data if r["family"]==kind]
    body='<p class="intro">Aggregate release coverage only. Exact identifier and state matches are candidates, not proof of controlling ownership, legal title, a complete portfolio or current responsibility. Individual owner records are excluded; row-level organizational projections are not published.</p>'
    body+='<div class="subnav">'+record_link("/ownership-coverage",{},"All evidence")+''.join(record_link("/ownership-coverage",{"kind":k},v) for k,v in labels.items())+'</div>'
    body+='<h2>'+esc(labels.get(kind,"Loaded PECOS releases"))+'</h2>'+release_table(data)
    if not data:
        body+='<p>No qualifying release for this selection is loaded in the current database.</p>'
    return layout("Ownership evidence coverage","/ownership-coverage",body)

def global_search(db,params):
    q=params.get("q","").strip()[:160]
    mode=params.get("mode","text")
    if mode not in ("text","identifier"):
        raise ValueError("unsupported search mode")
    state=params.get("state","")
    if state and state not in STATES:
        raise ValueError("invalid jurisdiction")
    if not q:
        return {"q":q,"mode":mode,"groups":[]}
    common={"identifier" if mode=="identifier" else "q":q}
    if state:
        common["state"]=state
    return {"q":q,"mode":mode,"groups":[
        {"kind":"facilities","label":"Care Compare provider records","params":common,
         "result":paged(db,"facilities",{**common,"limit":"6"})},
        {"kind":"certifications","label":"Certification and laboratory registry records","params":common,
         "result":registry_search(db,{**common,"limit":"6"})}]}

def render_search(db,params):
    result=global_search(db,params)
    body='<p class="intro">Search provider names, reported addresses, cities, ZIP codes and identifiers across loaded Care Compare and certification registries. Records remain separate; similar names and identifiers are not resolved physical facilities.</p>'
    body+='<form class="filters" method="get" action="/search" role="search"><label>Search<input name="q" value="'+esc(result["q"])+'" placeholder="Name, location, CCN or CLIA number"></label>'+select("mode","Match",[("text","Text / partial"),("identifier","Exact identifier")],params)+select("state","State / territory",[(s,s) for s in STATES],params)+'<button>Search</button><a href="/search">Reset</a></form>'
    if not result["q"]:
        body+='<div class="empty">Enter a name, location or identifier to begin. For exact identifier matching, choose Exact identifier.</div>'
    for group in result["groups"]:
        data=group["result"]
        body+='<h2>'+esc(group["label"])+' · '+fmt(data["total"])+'</h2>'
        if group["kind"]=="facilities":
            cells=[[record_link("/facility",{"dataset":r["dataset"],"ccn":r["ccn"]},r["name"],"record"),esc(r["ccn"]),esc(r["category"]),esc(r["address"]+" · "+r["city"]+", "+r["state"]+" "+r["zip"])] for r in data["rows"]]
        else:
            cells=[[record_link("/certification",{"registry":r["registry"],"row":r["row_number"]},r["name"] or "Unnamed source record","record"),esc(r["provider_id"] or "Not reported"),esc(r["registry"]),esc(r["address"]+" · "+r["city"]+", "+r["state"]+" "+r["zip"])] for r in data["rows"]]
        body+=table(["Record","Identifier","Source / type","Reported location"],cells)
        body+='<p>'+record_link("/"+group["kind"],group["params"],"View all "+fmt(data["total"])+" matching records")+'</p>'
    return layout("Unified search","/search",body)

def render_certification_detail(db,params):
    registry=params.get("registry","")
    try:
        number=int(params.get("row",""))
    except ValueError:
        raise ValueError("invalid registry row")
    if number<1:
        raise ValueError("invalid registry row")
    r=db.execute("SELECT c.*,r.title,r.period,r.imported_at,r.download_url FROM certification_records c JOIN certification_releases r ON r.registry=c.registry WHERE c.registry=? AND c.row_number=?",(registry,number)).fetchone()
    if not r:
        return None
    fields=[("Source identifier",r["provider_id"]),("Registry",r["registry"]),("Reported address",r["address"]+" "+r["city"]+" "+r["state"]+" "+r["zip"]),("Provider type code",r["provider_type"]),("Subtype code",r["subtype"]),("Certification date",r["certification_date"]),("Termination date",r["termination_date"]),("Source status code",r["status"]),("Release period",r["period"]),("Imported",r["imported_at"][:10]),("Source row number",r["row_number"]),("Source row SHA-256",r["row_sha256"])]
    body='<p class="intro">Source-specific registry record. Historical or terminated providers may be listed. Source-native codes are not interpreted as current operating or compliance status.</p><div class="details">'+''.join('<article><small>'+esc(k)+'</small><strong>'+esc(v or "Not reported")+'</strong></article>' for k,v in fields)+'</div><p>'+source_anchor(r["download_url"])+' · '+record_link("/certifications",{"registry":registry},"Browse this registry")+'</p>'
    return layout(r["name"] or "Certification record","/certifications",body)

def render_list(db, kind, params):
    result = sources(params) if kind=="sources" else paged(db,kind,params)
    body = filters(params,kind)
    if kind=="facilities":
        headers = ["Provider / CCN","Type","Reported location","Capacity","Reported ownership / chain","Source release"]
        dates={r["id"]:r["published_on"] for r in rows(db,"SELECT id,published_on FROM releases")}
        data=[[record_link("/facility",{"dataset":r["dataset"],"ccn":r["ccn"]},r["name"],"record")+'<small>'+esc(r["ccn"])+'</small>',
               esc(r["category"]),esc(r["city"]+", "+r["state"]+" "+r["zip"])+'<small>'+esc(r["address"])+'</small>',
               esc(r["capacity"] or "Not reported")+('<small>Certified beds</small>' if r["capacity"] and r["dataset"]=="nursing" else '<small>Dialysis stations</small>' if r["capacity"] and r["dataset"]=="dialysis" else ""),
               esc(r["ownership"] or "Not reported")+'<small>'+esc(r["chain"])+'</small>',
               esc(dates.get(r["release_id"],"Not recorded"))+'<small>'+source_anchor(source_url(r["dataset"]))+'</small>'] for r in result["rows"]]
        body='<p class="intro">Source-scoped Care Compare provider records, not resolved physical facilities. Capacity is shown as reported; status is not inferred.</p>'+body
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
    from ownership_evidence import profile
    if dataset in ("hospital","rehabilitation","long-term-hospital","nursing"):
        own=profile(db,dataset,ident)
        body += '<h2>Organizational ownership evidence</h2>'
        if own["enrollment_rows"] is None:
            body += '<p>Qualified ownership evidence not available for this profile.</p>'
        else:
            body += '<p>'+fmt(own["enrollment_rows"])+' same-state enrollment candidate rows · '+fmt(own["organization_role_rows"])+' linked organizational role rows. '+esc(own["note"])+'</p><p>Enrollment source: '+esc(own["enrollment_release"]["modified"])+' · '+source_anchor(own["enrollment_release"]["url"])+'</p>'
    body += '<h2>Additional intelligence</h2><div class="roadmap">Water, equipment, physical property ownership and contracts have not been integrated. Unknown is not zero.</div>'
    return layout(r["name"],"/facilities",body)

def registry_search(db, params):
    p,l=page_args(params)
    clauses,values=[],[]
    for k in ("registry","state"):
        if params.get(k):
            clauses.append(k+"=?")
            values.append(params[k])
    if params.get("identifier"):
        clauses.append("provider_id=?")
        values.append(params["identifier"].strip().upper())
        if not params.get("registry"):
            clauses.append("registry IN (SELECT registry FROM certification_releases)")
    q=params.get("q","").strip()[:160]
    if q:
        pattern="%"+q.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
        clauses.append("(provider_id LIKE ? ESCAPE '\\' OR name LIKE ? ESCAPE '\\' OR city LIKE ? ESCAPE '\\' OR address LIKE ? ESCAPE '\\' OR zip LIKE ? ESCAPE '\\')")
        values.extend([pattern]*5)
    where=" WHERE "+" AND ".join(clauses) if clauses else ""
    n=db.execute("SELECT count(*) FROM certification_records"+where,values).fetchone()[0]
    data=rows(db,"SELECT * FROM certification_records"+where+" ORDER BY name COLLATE NOCASE,registry,row_number LIMIT ? OFFSET ?",values+[l,(p-1)*l])
    releases=rows(db,"SELECT * FROM certification_releases ORDER BY registry")
    return {"rows":data,"total":n,"page":p,"limit":l,"releases":releases,"note":"Source registry records, including historical/terminated records; not unique active providers."}

def render_certifications(db,params):
    result=registry_search(db,params)
    form='<form class="filters" method="get"><label>Search<input name="q" value="'+esc(params.get("q",""))+'" placeholder="Name, provider number, city"></label><label>Exact identifier<input name="identifier" value="'+esc(params.get("identifier",""))+'"></label>'+select("registry","Registry",[("qies","QIES"),("iqies","iQIES"),("clia","CLIA")],params)+select("state","State / territory",[(s,s) for s in STATES],params)+'<button>Search</button><a href="/certifications">Reset</a></form>'
    body='<p class="intro">CMS certification records are stored separately from Care Compare providers. Historical and terminated records are included. Status and provider-type codes are source-native; do not infer an active facility from a listed record.</p>'
    body+=table(["Registry","Release period","Source rows"],[[esc(x["registry"]),esc(x["period"]),fmt(x["row_count"])] for x in result["releases"]])+form
    body+=table(["Provider / identifier","Registry","Location","Type code","Certification / termination"],[[record_link("/certification",{"registry":r["registry"],"row":r["row_number"]},r["name"] or "Unnamed source record","record")+'<small>'+esc(r["provider_id"] or "No source ID")+'</small>',esc(r["registry"]),esc(r["address"]+" "+r["city"]+" "+r["state"]+" "+r["zip"]),esc(r["provider_type"] or "Not reported"),esc(r["certification_date"] or "Not reported")+'<small>Termination: '+esc(r["termination_date"] or "Not reported")+'</small><small>Status: '+esc(r["status"] or "Not reported")+'</small>'] for r in result["rows"]])
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
                        if kind=="search":
                            return self.send(200,json.dumps(global_search(db,params)),"application/json; charset=utf-8")
                        if kind=="ownership-evidence":
                            from ownership_evidence import profile
                            return self.send(200,json.dumps(profile(db,params.get("dataset",""),params.get("ccn",""))),"application/json; charset=utf-8")
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
                    elif path=="/search":
                        body=render_search(db,params)
                    elif path=="/certification":
                        body=render_certification_detail(db,params)
                    elif path=="/ownership-coverage":
                        body=render_ownership_coverage(db,params)
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
