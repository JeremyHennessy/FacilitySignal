"""Conservative offline review of an explicitly source-labeled CMS provider ID.

No identifier inference, geocoding, network, event attribution or provider row output.
"""
from collections import Counter
import re
from unicodedata import normalize

CCN = re.compile(r"[0-9]{2}[A-Z0-9]{4}")
STATE = re.compile(r"[A-Z]{2}")
ZIP = re.compile(r"([0-9]{5})(?:-[0-9]{4})?")
SUFFIXES = {"STREET":"ST", "AVENUE":"AVE", "DRIVE":"DR", "ROAD":"RD"}
LABELS = {"CCN", "CMS Certification Number", "CMS Certification Number (CCN)"}

def norm(raw):
    return " ".join(normalize("NFC",raw).upper().split()) if isinstance(raw,str) else ""

def address_key(row):
    addr,city,state,zip_code = (norm(row.get(k)) for k in ("address","city","state","zip"))
    z=ZIP.fullmatch(zip_code)
    if not re.fullmatch(r"[0-9]+[A-Z]? [A-Z0-9 .'-]+",addr) or not city or not STATE.fullmatch(state) or not z:
        return None
    tokens=addr.split()
    term=tokens[-1].removesuffix(".")
    if term in SUFFIXES or term in SUFFIXES.values():
        tokens[-1]=SUFFIXES.get(term,term)
    return " ".join(tokens),city,state,z[1]

def classify(notice, directory):
    """Each notice needs its own explicit label; the directory is contemporary context only."""
    key=address_key(notice)
    address_matches=sum(key is not None and address_key(row)==key for row in directory)
    label=notice.get("identifier_label")
    ccn=notice.get("identifier_value")
    if label not in LABELS:
        return ("missing_explicit_ccn_unique_address_candidate" if address_matches==1 else
                "missing_explicit_ccn_multiple_address_candidates" if address_matches>1 else
                "missing_explicit_ccn_no_address_candidate")
    if not isinstance(ccn,str) or not CCN.fullmatch(ccn):
        return "unsupported_explicit_ccn"
    records=[row for row in directory if row.get("ccn")==ccn]
    if len(records)!=1:
        return "explicit_ccn_absent_or_ambiguous_in_directory"
    if key is None or address_key(records[0])!=key or address_matches!=1:
        return "explicit_ccn_address_not_corroborated"
    return "review_candidate_explicit_ccn_and_unique_address"

def aggregate(notices,directory):
    """Return counts only; repeated notices are not joined or collapsed."""
    return {"notices_checked":len(notices),"linkage_review_counts":dict(Counter(classify(n,directory) for n in notices)),
            "verification_scope":"Text-rendered notices and contemporary source directory. Not a historical case, ownership, or event crosswalk.",
            "canonical_provider_links":0,"provider_or_case_rows_emitted":0}
