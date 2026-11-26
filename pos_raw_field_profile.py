"""Profile every column of a pinned POS CSV without retaining raw data or changing the application.

Exact headers and source bytes are mandatory. Output counts only: lexical shape is
not a field definition, documented mapping matches are not publication approval.
"""
import argparse
import csv
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import tempfile

from collect_registry import source_encoding, open_csv
from restore_snapshot import verify_raw, materialize

ROOT = Path(__file__).resolve().parent
LOCK = ROOT / "research/snapshot_release_20261125.json"
INVENTORY = ROOT / "research/pos_field_inventory_q3_2026.json"
DICT = ROOT / "research/iqies_full_dictionary_metadata_20261126.json"
SEMANTICS = ROOT / "research/iqies_semantic_application_crosswalk_20261126.json"
CAP = 2048
M1_SCOPES = {"3":"HHA","4":"PRTF","5":"PXR","6":"OPT/SLP","7":"ESRD",
             "8":"ICFIID","9":"RHC","10":"CORF","11":"ASC","12":"HOSPICE",
             "13":"OPO","14":"CMHC","15":"FQHC","20":"NH"}
NUMBER = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?\Z")
INT = re.compile(r"[+-]?[0-9]+\Z")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
SLASH_DATE = re.compile(r"[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}\Z")
MISSING = {"":"blank", "not applicable":"not_applicable", "not available":"not_available",
           "unknown":"literal_unknown"}
def need(test, msg):
    if not test:
        raise ValueError(msg)
def read(path):
    return json.loads(path.read_text(encoding="utf-8"))
def scope_for(raw):
    return M1_SCOPES.get(raw.strip(), "UNKNOWN_PROVIDER_CODE")
def applicability(spec, scope):
    if not spec or spec["semantic_review"].startswith("blocked") or scope == "UNKNOWN_PROVIDER_CODE":
        return "scope_unresolved"
    s = spec["publisher_applicability"]
    if not s:
        return "scope_unresolved"
    s = s.upper().strip()
    if s == "ALL":
        return "applicable"
    # Publisher typo "ALL expect for FQHC" remains unresolved, not silently repaired.
    if s == "ALL EXPECT FOR FQHC":
        return "scope_unresolved"
    if s.startswith("ALL EXCEPT FOR "):
        excluded = {v.strip() for v in s[15:].split(",")}
        return "out_of_scope" if scope in excluded else "applicable"
    valid = {v.strip() for v in s.split(",")}
    if "OPT" in valid and scope == "OPT/SLP":
        return "scope_unresolved"
    if "HOSPITAL" in valid:
        return "scope_unresolved"
    return "applicable" if scope in valid else "out_of_scope"

def mapping_codes(spec, scope, mappings):
    if not spec or applicability(spec, scope) != "applicable":
        return None
    mapping = spec["mapping_reference"]
    if mapping and mapping.startswith("M8 ("):
        if scope != "HHA":
            return None
        mapping = "M8"
    if mapping not in mappings:
        return None
    accepted = {}
    for row in mappings[mapping]["entries"]:
        scopes = row["provider_types"]
        if scopes is not None and scope not in {v.strip().upper() for v in scopes.split(",")}:
            continue
        code = row["code"]
        need(code not in accepted, "duplicate applicable publisher code")
        accepted[code] = row["row"]
    return accepted

def shape(v):
    if v.isascii() and v.isdigit():
        return "unsigned_integer_text"
    if INT.fullmatch(v):
        return "signed_integer_text"
    if NUMBER.fullmatch(v):
        return "decimal_text"
    if DATE.fullmatch(v):
        return "iso_date_shape"
    if SLASH_DATE.fullmatch(v):
        return "slash_date_shape"
    return "other_text"

class FieldProfile:
    def __init__(self, spec=None, mappings=None):
        self.spec = spec
        self.mappings = mappings or {}
        self.states = Counter()
        self.shapes = Counter()
        self.distinct = set()
        self.capped = False
        self.max_len = 0
        self.by_scope = defaultdict(Counter)
        self.codes = defaultdict(Counter)
        self.domains = {}
        self.numerics = {}

    def add(self, raw, scope=None):
        v = raw.strip()
        token = MISSING.get(v.casefold())
        if token is not None:
            self.states[token] += 1
        else:
            self.states["other_nonblank"] += 1
            self.shapes[shape(v)] += 1
            self.max_len = max(self.max_len, len(v))
            if not self.capped:
                self.distinct.add(v)
                if len(self.distinct) > CAP:
                    self.capped = True
                    self.distinct.clear()
        if scope is None:
            return
        stats = self.by_scope[scope]
        app = applicability(self.spec, scope)
        stats["rows"] += 1
        stats[app] += 1
        if token is not None:
            stats[token] += 1
            if app == "applicable" and token == "not_applicable":
                stats["applicability_conflict"] += 1
            return
        stats["other_nonblank"] += 1
        if app != "applicable":
            stats[app + "_nonblank"] += 1
            return
        spec = self.spec
        if scope not in self.domains:
            self.domains[scope] = mapping_codes(spec, scope, self.mappings)
        codes = self.domains[scope]
        if codes is not None:
            if v in codes:
                stats["documented_code"] += 1
                self.codes[scope][v] += 1
            else:
                stats["unmatched_code_token"] += 1
            return
        kind = spec["interpretation_shape"]
        if kind == "boolean":
            if v.casefold() in ("yes","no"):
                stats["reported_" + v.casefold()] += 1
            else:
                stats["unmatched_boolean_token"] += 1
        elif kind in ("count_integer","fte_decimal"):
            if len(v) <= 30 and NUMBER.fullmatch(v):
                n = Decimal(v)
                if n >= 0 and (kind == "fte_decimal" or n == n.to_integral_value()):
                    stats["nonnegative_numeric"] += 1
                    stats["explicit_zero"] += int(n == 0)
                    if kind == "count_integer" and not INT.fullmatch(v):
                        stats["integer_value_decimal_spelling"] += 1
                    old = self.numerics.get(scope)
                    self.numerics[scope] = (n,n,n) if old is None else (
                        min(n,old[0]),max(n,old[1]),old[2]+n)
                    return
            stats["unmatched_numeric_token"] += 1

    def result(self, total):
        need(sum(self.states.values()) == total, "field state reconciliation")
        need(sum(self.shapes.values()) == self.states["other_nonblank"], "shape reconciliation")
        if self.by_scope:
            need(sum(v["rows"] for v in self.by_scope.values()) == total, "scope reconciliation")
            for k,v in self.by_scope.items():
                need(sum(v[s] for s in ("applicable","out_of_scope","scope_unresolved")) == v["rows"],
                     "applicability count reconciliation")
                need(sum(v[s] for s in (*MISSING.values(),"other_nonblank")) == v["rows"],
                     "scope missing state reconciliation")
                need(sum(self.codes[k].values()) == v["documented_code"], "code count reconciliation")
        return {"states":dict(self.states),"lexical_shapes":dict(self.shapes),
                "distinct_nonmissing":{"count":CAP+1 if self.capped else len(self.distinct),
                                       "method":"lower_bound" if self.capped else "exact"},
                "max_nonmissing_trimmed_length":self.max_len,
                "scope_counts":{k:dict(v) for k,v in self.by_scope.items()},
                "documented_code_counts":{k:dict(v) for k,v in self.codes.items() if v},
                "numeric_aggregate_by_scope":{k:{"min":str(v[0]),"max":str(v[1]),"sum":str(v[2])}
                  for k,v in self.numerics.items()
                  if self.spec and not (self.spec["anomaly"] and
                       self.spec["anomaly"]["kind"]=="blocking_for_aggregation")}}

def run(source, path, item, inventory, semantic=None, dictionary=None):
    verify_raw(path,item)
    expected = [f["field"] for f in inventory["fields"]]
    need(inventory["source_sha256"] == item["sha256"], "inventory source digest mismatch")
    need(inventory["source_rows"] == item["input_rows"], "inventory source count mismatch")
    need(len(expected) == len(set(expected)), "duplicate inventory header")
    spec = {}
    mapping = {}
    if source == "iqies":
        need(semantic and dictionary, "iQIES semantic metadata missing")
        spec = {f["field"]:f for f in semantic["fields"]}
        need(list(spec) == expected, "semantic field order mismatch")
        mapping = dictionary["mapping_sheets"]
        need({r["code"] for r in mapping["M1"]["entries"]} == set(M1_SCOPES),
             "provider scope domain mismatch")
    stats = [FieldProfile(spec.get(f),mapping) for f in expected]
    encoding = source_encoding(path,item["metadata"]["zipped"])
    n = 0
    scopes = Counter()
    with open_csv(path,item["metadata"]["zipped"],encoding) as stream:
        reader = csv.reader(stream)
        header = next(reader,[])
        need(header == expected, "exact pinned raw header mismatch")
        ix = expected.index("prvdr_type_id") if source == "iqies" else None
        for row in reader:
            n += 1
            need(len(row) == len(expected), "raw row width mismatch at ordinal "+str(n))
            scope = scope_for(row[ix]) if ix is not None else None
            if scope is not None:
                scopes[scope] += 1
            for profile,value in zip(stats,row):
                profile.add(value,scope)
    need(n == item["input_rows"], "raw row count mismatch")
    verify_raw(path,item)
    fields = [{"ordinal":i+1,"field":f,**p.result(n)} for i,(f,p) in enumerate(zip(expected,stats))]
    return {"format_version":1,"source":source,"period":item["release"],"source_sha256":item["sha256"],
            "source_bytes":item["bytes"],"encoding":encoding,"rows":n,"columns":len(expected),
            "provider_scope_counts":dict(scopes),"fields":fields,
            "limits":["Counts only; no source values except exact matched publisher dictionary codes.",
                      "Shape is lexical, not semantic. Blank, Not Applicable, Not Available and Unknown differ.",
                      "Distinct count is capped; lower_bound is not an exact count.",
                      "Scope and code comparisons are provisional, exact trimmed tokens; no guessed mapping.",
                      "Numeric sums are single field and provider scope only; not unique properties, staffing shifts or installed assets.",
                      "No operational, equipment, procurement, or reuse approval."]}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",choices=("qies","iqies","clia"),required=True)
    p.add_argument("--raw-dir",type=Path)
    p.add_argument("--download",action="store_true")
    p.add_argument("--output",type=Path,required=True)
    a = p.parse_args()
    need(not a.output.exists(),"new output required")
    lock = read(LOCK)
    item = next(x for x in lock["sources"] if x["key"]==a.source)
    inv = read(INVENTORY)["registries"][a.source]
    with tempfile.TemporaryDirectory(prefix="pos-field-profile-") as d:
        path = materialize(item,a.raw_dir,Path(d),a.download)
        result = run(a.source,path,item,inv,read(SEMANTICS) if a.source=="iqies" else None,
                     read(DICT) if a.source=="iqies" else None)
    with a.output.open("x",encoding="utf-8") as f:
        json.dump(result,f,indent=2,sort_keys=True)
        f.write("\n")
    # One aggregate-only compact row per field, so results can be reviewed independently.
    print("POS_PROFILE_SUMMARY",json.dumps({k:v for k,v in result.items() if k!="fields"},sort_keys=True),flush=True)
    for field in result["fields"]:
        print("POS_PROFILE_FIELD",json.dumps(field,separators=(",",":"),sort_keys=True),flush=True)

if __name__ == "__main__":
    main()
