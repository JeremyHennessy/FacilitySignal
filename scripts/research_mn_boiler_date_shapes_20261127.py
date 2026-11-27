"""Offline date-shape checks for the pinned DLI edition; no data loading or row output."""
from datetime import date
import re

SNAPSHOT = date(2026, 11, 27)
HEADER = (
    "Asset_Number", "Asset_Type", "MNB_Number", "Serial_Number", "NB_Number",
    "Last_Inspection_Date", "Inspection_Type", "Expiration_Date", "Asset_SubType",
    "Asset_Use", "Fuel_Type", "Manufacturer", "Year_Built", "MAWP",
    "Heating_Surface", "Max_BTU_Input", "Milestone", "Business_Name",
    "Location_Address1", "Location_Address2", "Location_City", "Location_County",
    "Location_Zip", "Owner_Name", "Owner_Address1", "Owner_Address2", "Owner_City",
    "Owner_State", "Owner_Zip", "Legacy_Site_No", "Location_Record_ID",
)

def verify_header(fields):
    if tuple(fields) != HEADER:
        raise ValueError("Unexpected pinned DLI header")

def parse_date(raw):
    """Provisional exact shape: ISO date or published-US-context slash date. No timestamps."""
    if not isinstance(raw, str):
        return "unsupported", None
    raw = raw.strip()
    if not raw:
        return "missing", None
    iso = re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})", raw)
    us = re.fullmatch(r"([0-9]{1,2})/([0-9]{1,2})/([0-9]{4})", raw)
    if iso:
        year, month, day = map(int, iso.groups())
    elif us:
        month, day, year = map(int, us.groups())
    else:
        return "unsupported", None
    try:
        return "parseable", date(year, month, day)
    except ValueError:
        return "invalid_calendar", None

def date_buckets(row):
    """Return categorical observations only; no raw values or inferred certificate status."""
    last_parse, last = parse_date(row["Last_Inspection_Date"])
    exp_parse, exp = parse_date(row["Expiration_Date"])
    last_rel = (last_parse if last is None else
                "before_snapshot" if last < SNAPSHOT else
                "on_snapshot" if last == SNAPSHOT else "after_snapshot")
    exp_rel = (exp_parse if exp is None else
               "before_snapshot" if exp < SNAPSHOT else
               "on_snapshot_unresolved" if exp == SNAPSHOT else "after_snapshot")
    relative = ("not_comparable" if last is None or exp is None else
                "last_before_expiration" if last < exp else
                "same_date" if last == exp else "last_after_expiration")
    return last_rel, exp_rel, relative
