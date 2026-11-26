"""FDA MQSA public directory: bounded, ephemeral projection; aggregate evidence only."""
import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import stat
import tempfile
import urllib.request
import zipfile
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

URL = "https://www.accessdata.fda.gov/premarket/ftparea/public.zip"
DOC = "https://www.fda.gov/radiation-emitting-products/mammography-information-patients/search-certified-mammography-facility"
WIDTHS = (75, 50, 50, 50, 50, 2, 15, 50, 50)
FIELDS = ("name", "address1", "address2", "address3", "city", "state", "zip", "phone", "fax")
JURISDICTIONS = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR VI".split())
MILITARY_MAIL = {"AA", "AE", "AP"}
MAX_ZIP = 12 * 1024 * 1024
MAX_TEXT = 24 * 1024 * 1024

def require(ok, message):
    if not ok:
        raise ValueError(message)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("unexpected FDA download redirect")

def download(path):
    opener = urllib.request.build_opener(NoRedirect())
    req = urllib.request.Request(URL, headers={"User-Agent": "FacilitySignal institutional source qualification", "Accept": "application/x-zip-compressed,application/zip,application/octet-stream"})
    digest = hashlib.sha256()
    count = 0
    with opener.open(req, timeout=60) as res, path.open("xb") as out:
        require(res.geturl() == URL, "unexpected source URL")
        length = res.headers.get("Content-Length")
        if length:
            require(0 < int(length) <= MAX_ZIP, "download size")
        while chunk := res.read(65536):
            count += len(chunk)
            require(count <= MAX_ZIP, "download size")
            digest.update(chunk)
            out.write(chunk)
        require(count and (not length or count == int(length)), "incomplete response")
        return {"url": URL, "documentation": DOC, "bytes": count, "sha256": digest.hexdigest(),
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "last_modified": res.headers.get("Last-Modified"),
                "etag": res.headers.get("ETag")}

def archive_bytes(path):
    require(0 < path.stat().st_size <= MAX_ZIP, "archive size")
    with zipfile.ZipFile(path) as z:
        members = z.infolist()
        require(len(members) == 1, "unexpected archive member count")
        m = members[0]
        require(not m.is_dir() and re.fullmatch(r"[A-Za-z0-9_.-]+", m.filename) and m.filename not in {".", ".."}, "unsafe member")
        require(stat.S_IFMT(m.external_attr >> 16) in (0, stat.S_IFREG), "nonregular archive member")
        require(not m.flag_bits & 1 and 0 < m.file_size <= MAX_TEXT, "unsafe member size or encryption")
        with z.open(m) as stream:
            raw = stream.read(MAX_TEXT + 1)
        require(len(raw) == m.file_size, "expanded size mismatch")
        return raw

def fixed(line):
    require(292 <= len(line) <= sum(WIDTHS), "fixed width mismatch")
    line = line.ljust(sum(WIDTHS))
    out = []
    at = 0
    for width in WIDTHS:
        out.append(line[at:at+width])
        at += width
    return out

def row_valid(row):
    return (len(row) == len(WIDTHS) and all(len(v) <= w for v, w in zip(row, WIDTHS))
            and bool(row[0].strip()) and bool(row[4].strip()) and bool(re.fullmatch(r"[A-Z]{2}", row[5].strip()))
            and all(not any(ord(c) < 32 or ord(c) == 127 for c in v) for v in row))

def parse_line(line, layout):
    if layout == "fixed":
        return fixed(line)
    return next(csv.reader([line], delimiter={"tab":"\t", "pipe":"|", "comma":","}[layout], strict=True))

def audit_archive(db, path):
    raw = archive_bytes(path)
    try:
        txt = raw.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        txt = raw.decode("cp1252")
        encoding = "cp1252"
    # No guessing based on a single row; every layout competes on the full file.
    lines = txt.splitlines()
    require(0 < len(lines) <= 100000, "unexpected line count")
    nonblank = [line for line in lines if line.strip()]
    require(nonblank, "empty source")
    candidates = {}
    parsed = {}
    for layout in ("fixed", "tab", "pipe", "comma"):
        rows = []
        for ordinal, line in enumerate(nonblank, 1):
            try:
                row = parse_line(line, layout)
                if row_valid(row):
                    rows.append((ordinal, row))
            except (ValueError, csv.Error):
                pass
        candidates[layout] = len(rows)
        if len(rows) == len(nonblank):
            parsed[layout] = rows
    base = {"expanded_bytes": len(raw), "encoding": encoding, "physical_lines":len(lines),
            "blank_lines": len(lines)-len(nonblank), "input_rows":len(nonblank),
            "layout_valid_row_counts":candidates, "field_widths":dict(zip(FIELDS,WIDTHS))}
    if len(parsed) != 1:
        return dict(base, qualification="schema_review_required", stored_rows=0,
                    unresolved_rows=len(nonblank), unique_layout=False)
    layout, rows = next(iter(parsed.items()))
    states, missing = Counter(), Counter()
    duplicates = 0
    seen = set()
    with db:
        db.execute("CREATE TABLE mqsa_projection(ordinal INTEGER PRIMARY KEY,name TEXT,address1 TEXT,address2 TEXT,address3 TEXT,city TEXT,state TEXT,zip TEXT)")
        for ordinal, original in rows:
            row = tuple(v.strip() for v in original)
            # Contact fields are never stored or retained; exact duplicate count includes them.
            digest = hashlib.sha256(json.dumps(original, ensure_ascii=False).encode()).digest()
            duplicates += int(digest in seen)
            seen.add(digest)
            db.execute("INSERT INTO mqsa_projection VALUES(?,?,?,?,?,?,?,?)", (ordinal,*row[:7]))
            state = row[5]
            states[state if state in JURISDICTIONS else "military_mail" if state in MILITARY_MAIL else "other"] += 1
            for field, value in zip(FIELDS[:7], row[:7]):
                if not value:
                    missing[field] += 1
        stored = db.execute("SELECT count(*) FROM mqsa_projection").fetchone()[0]
        unique = db.execute("SELECT count(*) FROM (SELECT DISTINCT name,address1,address2,address3,city,state,zip FROM mqsa_projection)").fetchone()[0]
        require(stored == len(nonblank) == sum(states.values()), "row reconciliation")
        require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLite integrity")
    return dict(base, qualification="ephemeral_projection_qualified", layout=layout, unique_layout=True,
                stored_rows=stored, unresolved_rows=0, exact_parsed_row_duplicates=duplicates,
                repeated_projected_name_address_rows=stored-unique, jurisdiction_counts=dict(sorted(states.items())),
                represented_us_jurisdictions=len(set(states)&JURISDICTIONS), missing_fields=dict(missing),
                stable_publisher_id_available=False, canonical_matches=0,
                limits="Source rows, not unique sites; no facility ID, certificate dates, inspection or equipment counts; VHA excluded; mobile classification incomplete; reuse review pending. No row-level artifact.")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--local-archive", type=Path, help="Use an existing authorized local copy; no network")
    a=p.parse_args()
    require(not a.audit.exists(), "audit exists")
    with tempfile.TemporaryDirectory(prefix="mqsa-") as tmp:
        path=a.local_archive or Path(tmp)/"source.zip"
        if a.local_archive:
            require(0 < path.stat().st_size <= MAX_ZIP, "archive size")
            with path.open("rb") as f:
                meta={"url":URL,"documentation":DOC,"bytes":path.stat().st_size,"sha256":hashlib.file_digest(f,"sha256").hexdigest(),"retrieved_at":None}
        else:
            meta=download(path)
        with closing(sqlite3.connect(":memory:")) as db:
            meta.update(audit_archive(db,path))
        with path.open("rb") as f:
            require(hashlib.file_digest(f,"sha256").hexdigest()==meta["sha256"],"archive changed")
        with a.audit.open("x", encoding="utf-8") as f:
            json.dump(meta,f,indent=2,sort_keys=True)
        print(json.dumps(meta,sort_keys=True))
    if meta["qualification"] != "ephemeral_projection_qualified":
        raise SystemExit("source schema needs review")

if __name__ == "__main__":
    main()
