"""Bounded USAspending federal contract-award source qualification.

One public award-search page, no private credentials or raw/public rows.
Award-level evidence is not an open notice, a healthcare property match,
a service need, or a total for the selected period.
"""
import argparse,hashlib,json,re,urllib.request,urllib.error
from datetime import date,datetime,timezone
from decimal import Decimal
from pathlib import Path
from collections import Counter
URL="https://api.usaspending.gov/api/v2/search/spending_by_award/"
AGENCY="Department of Veterans Affairs"
LIMIT=100
FIELDS=["Award ID","generated_internal_id","Awarding Agency","Awarding Sub Agency","Start Date","End Date","Award Amount","Contract Award Type","Place of Performance State Code","Place of Performance Country Code","Recipient UEI"]
REQUEST={"filters":{"award_type_codes":["A","B","C","D"],"agencies":[{"type":"awarding","tier":"toptier","name":AGENCY}],"time_period":[{"start_date":"2026-10-01","end_date":"2026-10-31"}]},"fields":FIELDS,"limit":LIMIT,"page":1,"sort":"Award Amount","order":"desc","spending_level":"awards"}
STATES=set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR VI".split())
def require(ok,msg):
    if not ok:raise ValueError(msg)
def date_state(v):
    if v in (None,""):return "missing"
    if not isinstance(v,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",v):return "unrecognized"
    try:date.fromisoformat(v);return "iso_date"
    except ValueError:return "unrecognized"
def amount_state(v):
    if v in (None,""):return "missing"
    if type(v) not in (int,Decimal,float):return "unrecognized"
    d=Decimal(str(v))
    if not d.is_finite():return "unrecognized"
    return "positive" if d>0 else "negative" if d<0 else "zero"
def classify_record(row):
    require(isinstance(row,dict) and set(FIELDS)<=set(row),"Award response field drift")
    key=row["generated_internal_id"]
    require(isinstance(key,str) and bool(key.strip()) and len(key)<=500,"Missing/invalid generated award identifier")
    require(row["Awarding Agency"]==AGENCY,"Unexpected awarding agency")
    # Do not use recipient name/addresses or descriptions. UEI presence is not
    # proof of a corporate recipient, contractor responsibility or facility link.
    return {"key":key,
            "award_id_present":isinstance(row["Award ID"],str) and bool(row["Award ID"].strip()),
            "amount":amount_state(row["Award Amount"]),
            "start":date_state(row["Start Date"]),"end":date_state(row["End Date"]),
            "contract_type_present":isinstance(row["Contract Award Type"],str) and bool(row["Contract Award Type"].strip()),
            "state_scope":"us_jurisdiction" if isinstance(row["Place of Performance State Code"],str) and row["Place of Performance State Code"] in STATES else "missing" if row["Place of Performance State Code"] in (None,"") else "other_uninterpreted",
            "uei_present":isinstance(row["Recipient UEI"],str) and bool(re.fullmatch(r"[A-Z0-9]{12}",row["Recipient UEI"])),
            "agency_scope":"awarding_department_only"}
def audit(payload):
    require(isinstance(payload,dict) and isinstance(payload.get("results"),list),"Unexpected response shape")
    rows=payload["results"];meta=payload.get("page_metadata",{})
    require(0<len(rows)<=LIMIT and meta.get("page")==1 and type(meta.get("hasNext")) is bool,"Missing/bad bounded page metadata")
    out=[classify_record(r) for r in rows];keys=[r["key"] for r in out]
    require(len(set(keys))==len(keys),"Duplicate award identifiers on sample page")
    return {"sample_rows":len(rows),"unique_generated_award_ids":len(set(keys)),"additional_pages_reported":meta["hasNext"],
            "amount_value_states":dict(Counter(r["amount"] for r in out)),"start_date_states":dict(Counter(r["start"] for r in out)),"end_date_states":dict(Counter(r["end"] for r in out)),
            "performance_state_scope_counts":dict(Counter(r["state_scope"] for r in out)),
            "award_id_present_count":sum(r["award_id_present"] for r in out),"contract_type_present_count":sum(r["contract_type_present"] for r in out),"uei_format_present_count":sum(r["uei_present"] for r in out),
            "confirmed_facility_relationships":0,"confirmed_active_opportunities":0,"retained_row_level_records":0,
            "scope":"One bounded award-search result page; VA awarding department only; all contract types A/B/C/D; October 2026 source search window, not necessarily award start dates; not all healthcare purchases or an award total for that period.",
            "limits":"No recipient, award identifier, address, description or amount values retained. Place of performance is source geography, not a site match. Award amounts are not active opportunity or spend-in-window totals. UEI syntax does not establish an organization or supplier relationship. Commercial reuse and linkage review pending."}
def fetch():
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise ValueError("Unexpected API redirect")
    body=json.dumps(REQUEST,separators=(",",":")).encode()
    req=urllib.request.Request(URL,data=body,headers={"Content-Type":"application/json","Accept":"application/json","User-Agent":"FacilitySignal source qualification/1.0"},method="POST")
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=60) as r:
        require(r.status==200 and r.geturl()==URL,"Unexpected publisher response")
        raw=r.read(2_000_001);require(len(raw)<=2_000_000,"Response exceeds sample byte cap")
    payload=json.loads(raw,parse_float=Decimal)
    report=audit(payload)
    report.update({"publisher":"USAspending.gov","url":URL,"request":REQUEST,"response_sha256":hashlib.sha256(raw).hexdigest(),"response_bytes":len(raw),"retrieved_at":datetime.now(timezone.utc).isoformat(),"reuse_review":"pending","qualification":"bounded_award_page_schema_and_grain"})
    return report
def main():
    p=argparse.ArgumentParser();p.add_argument("--audit",type=Path,required=True);a=p.parse_args()
    require(not a.audit.exists(),"New audit output required")
    try:report=fetch()
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError) as e:
        # No remote response body or individual award fields in logs.
        print("PROCUREMENT_ACCESS_BLOCKED",type(e).__name__,getattr(e,"code",None),flush=True);raise SystemExit(1)
    a.audit.parent.mkdir(parents=True,exist_ok=True)
    a.audit.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("PROCUREMENT_AUDIT",json.dumps(report),flush=True)
if __name__=="__main__":main()
