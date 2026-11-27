"""Compute aggregate Minnesota DLI/CMS site-key coverage. No row outputs."""
import argparse
import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

REQUIRED = {
    "Asset_Number", "Asset_Type", "Milestone", "Location_Record_ID",
    "Location_Address1", "Location_Address2", "Location_City", "Location_Zip",
    "Last_Inspection_Date", "Expiration_Date",
}
CMS = {
    "hospital": "222096b1bf7cfbfcb37c4c6375d6ba686c6e3ccdd7af47c542bfb91ad34d621a",
    "nursing": "36363899e56c97433686ce8617a7d4b557b272a155e8a8eba1822c6f7a36e3ce",
}
DLI = "7f745253a9c58e739d572cc88eddb8c84153c0458301642634f69ca4a91c3b4c"
SUFFIX = {"STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "DRIVE": "DR",
          "BOULEVARD": "BLVD", "LANE": "LN", "COURT": "CT", "CIRCLE": "CIR",
          "PARKWAY": "PKWY", "PLACE": "PL", "TRAIL": "TRL"}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def literal(s):
    return " ".join(unicodedata.normalize("NFC", s).strip().upper().split())

def key(address, line2, city, postal, suffix=False):
    a, b, c = (literal(v) for v in (address, line2, city))
    z = re.fullmatch(r"([0-9]{5})(?:-[0-9]{4})?", postal.strip())
    if not z or not c or not re.match(r"[0-9]+[A-Z]?(?:-[0-9]+)?\s", a) or b:
        return None
    if suffix:
        tokens = a.split()
        i = -2 if len(tokens)>2 and tokens[-1] in {"N","S","E","W","NE","NW","SE","SW"} else -1
        term = tokens[i].removesuffix(".")
        if term in SUFFIX or term in SUFFIX.values():
            tokens[i] = SUFFIX.get(term, term)
        a = " ".join(tokens)
    return a, c, z[1]

def profile(root):
    modes = (False, True)
    provider = {m: defaultdict(list) for m in modes}
    nprov = Counter()
    denominator = Counter()
    for source, digest in CMS.items():
        raw = (root / f"{source}.json").read_bytes()
        if sha(raw) != digest: raise ValueError("CMS source hash does not match")
        records = json.loads(raw)["records"]
        for row in records:
            if row["state"] != "MN": continue
            nprov[source] += 1
            for mode in modes:
                k = key(row["address"], "", row["city"], row["zip"], mode)
                if k:
                    provider[mode][k].append(source)
                    if not mode: denominator[source]+=1
    if nprov != {"hospital":136,"nursing":337}: raise ValueError("Unexpected Minnesota cohort")
    zbytes = (root / "source.zip").read_bytes()
    if len(zbytes) != 8082131 or sha(zbytes) != DLI: raise ValueError("DLI source hash does not match")
    dli = {m: defaultdict(Counter) for m in modes}
    location = {m: defaultdict(set) for m in modes}
    raw_ids, locations, typed, milestones = set(), set(), Counter(), Counter()
    n = dli_keyable = duplicate_asset = missing_asset = 0
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        members = z.infolist()
        if len(members) != 1: raise ValueError("Unexpected members")
        info = members[0]
        if (info.filename != "BPV_SNAP_11_27_2026.csv" or info.file_size!=58397370
            or info.CRC!=0x9885b6be or info.flag_bits & 1): raise ValueError("Unexpected member edition")
        with z.open(info) as f, io.TextIOWrapper(f, encoding="cp1252",errors="strict",newline="") as txt:
            reader = csv.DictReader(txt,strict=True)
            fields = reader.fieldnames or []
            if len(fields)!=31 or len(set(fields))!=31 or not REQUIRED<=set(fields): raise ValueError("Unexpected CSV header")
            for row in reader:
                if None in row or None in row.values(): raise ValueError("Malformed CSV row")
                n += 1
                if n > 200000: raise ValueError("Row cap")
                asset = row["Asset_Number"].strip()
                lid = row["Location_Record_ID"].strip()
                if not asset: missing_asset += 1
                elif asset in raw_ids: duplicate_asset += 1
                else: raw_ids.add(asset)
                if lid: locations.add(lid)
                atype = literal(row["Asset_Type"])
                bucket = "boiler" if atype == "BOILER" else "pressure_vessel" if atype == "PRESSURE VESSEL" else "other_or_unmapped"
                typed[bucket]+=1
                status = literal(row["Milestone"])
                milestones[status if status in {"ACTIVE","INACTIVE","EXPIRED","REMOVED","RETIRED","DELETED","CLOSED","VOID","CURRENT","ISSUED"} else "other_or_unmapped"]+=1
                for mode in modes:
                    k = key(row["Location_Address1"], row["Location_Address2"], row["Location_City"], row["Location_Zip"], mode)
                    if k and not mode: dli_keyable += 1
                    if k in provider[mode] and k is not None:
                        dli[mode][k][bucket] += 1
                        location[mode][k].add(lid)
    groups={}
    for mode in modes:
        m=Counter(); a=Counter(); by=Counter(); single=Counter()
        for k, pc in provider[mode].items():
            m["provider_address_keys"]+=1
            if len(pc)>1: m["multi_provider_address_keys"]+=1
            if k not in dli[mode]: continue
            for p in pc: by[p]+=1
            multi_lid=len(location[mode][k])!=1 or "" in location[mode][k]
            m["matched_address_keys"]+=1
            m["matched_with_boiler_rows"]+=bool(dli[mode][k]["boiler"])
            m["matched_with_multi_provider_records"]+=len(pc)>1
            m["matched_with_multiple_or_unset_dli_location_ids"]+=multi_lid
            if len(pc)==1 and not multi_lid:
                m["one_provider_one_dli_location_id_keys"]+=1
                single[pc[0]]+=1
                m["unambiguous_key_with_boiler_rows"]+=bool(dli[mode][k]["boiler"])
            a.update(dli[mode][k])
        groups["street_suffix_only" if mode else "literal"]={"address_metrics":dict(m),"provider_records_with_candidates":dict(by),"one_provider_one_dli_site_by_source":dict(single),"asset_source_rows_at_matched_keys":dict(a)}
    return {"status":"AGGREGATE_RESEARCH_ONLY","dli_source":{"sha256":DLI,"archived_bytes":len(zbytes),"local_csv_member":info.filename,"member_crc32":"9885b6be","rows_screened":n,"distinct_nonempty_asset_tokens":len(raw_ids),"duplicate_nonempty_asset_rows":duplicate_asset,"missing_asset_rows":missing_asset,"distinct_dli_location_tokens":len(locations),"literal_address_keyable_rows":dli_keyable,"asset_type_literal_buckets":typed,"milestone_literal_buckets":milestones,"actual_header":fields},
            "cms_pack_sha256":CMS,"cms_minnesota_provider_rows":nprov,"cms_keyable_minnesota_provider_rows":denominator,"matching":groups,
            "scope":"Address/city/ZIP5 candidate co-location only, not asset ownership, installed/in-service equipment, operator, compliance, demand or vendor link. Only location (not owner) used. Multi-provider and DLI-site ambiguity stay distinct; one-to-one key still requires source review. No row/address/ID output, Azure write or promotion."}

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("source_directory",type=Path)
    arg=parser.parse_args()
    print(json.dumps(profile(arg.source_directory),sort_keys=True,indent=2))
