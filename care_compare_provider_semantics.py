"""Hospital and nursing provider-file semantic diagnostics, aggregate only.

No new source publication, risk score, address, coordinates, contact data, or
provider-level output. Publisher text and rendered dictionary revisions differ;
the review status explicitly preserves that uncertainty. Never coerce blanks.
"""
import argparse,csv,json,re,tempfile
from collections import Counter,defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from restore_snapshot import materialize,verify_raw
from pos_raw_field_profile import read,need,LOCK

ROOT=Path(__file__).resolve().parent
HEADERS=ROOT/"research/care_compare_pecos_exact_headers_20261126.json"
PROFILES=ROOT/"research/care_compare_directory_raw_field_profiles_20261126.json"
SOURCES=("hospital","nursing")
DOCS={"hospital":"https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/hospital/HOSPITAL_Data_Dictionary.pdf",
      "nursing":"https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/nursing_home/NH_Data_Dictionary.pdf"}
NH_FOOTNOTES={"1","2","6","7","9","10","13","14","18","20","21","22","23","24","25","26","27","28","29"}
NH_FLAGS={
 "Urban":"Publisher urban/rural classification; not building density.",
 "Provider Resides in Hospital":"Reported nursing provider located in a hospital; not an exact hospital identity link.",
 "Continuing Care Retirement Community":"Reported continuing-care retirement community indicator; not verified ownership.",
 "Abuse Icon":"Publisher threshold-based indicator of abuse/neglect citations in specified survey cycles; not proof of a current incident.",
 "High Performing Icon":"Newer publisher text describes an indicator for higher-performing nursing homes; image revision lacks this field.",
 "Most Recent Health Inspection More Than 2 Years Ago":"Publisher inspection-age flag at snapshot; not a present-day overdue determination.",
 "Provider Changed Ownership in Last 12 Months":"Publisher retrospective change indicator; not a property transfer or verified current owner."}
ENUMS={
 "Hospital Type":("Acute Care Hospitals","Critical Access Hospitals","Psychiatric","Childrens","Children's","Department of Defense","Acute Care - Veterans Administration","Rural Emergency Hospitals","Other"),
 "Hospital Ownership":("Government - Hospital District or Authority","Government - Federal","Government - Local","Government - State","Government - City","Government - County","Government - City/County","Government - Other","Voluntary non-profit - Private","Voluntary non-profit - Church","Voluntary non-profit - Other","Proprietary","Physician","Tribal","Other"),
 "Emergency Services":("Yes","No"),
 "Meets criteria for birthing friendly designation":("Y","N"),
 "Automatic Sprinkler Systems in All Required Areas":("Yes","Partial","No","Data Not Available"),
 "Special Focus Status":("SFF","SFF Candidate"),
 "With a Resident and Family Council":("Resident","Family","Both","None","Resident Council","Family Council"),
}
NH_RATINGS=("Overall Rating","Health Inspection Rating","QM Rating","Long-Stay QM Rating","Short-Stay QM Rating","Staffing Rating")
GROUPS={"MORT":8,"Safety":8,"READM":11,"Pt Exp":15,"TE":10}
MISSING={"":"blank","not available":"not_available","not applicable":"not_applicable","data not available":"not_available","n/a":"not_applicable","na":"literal_na","-":"dash","unknown":"unknown","suppressed":"suppressed"}
IDENTITY={"Facility ID","CMS Certification Number (CCN)","Facility Name","Provider Name","Legal Business Name"}
GEO={"Address","Provider Address","City/Town","State","ZIP Code","County/Parish","Provider SSA County Code","Location","Latitude","Longitude"}
def semantic(source,f):
    if f=="Telephone Number":return ("restricted_contact","Telephone presence only; no contact values published.","presence")
    if f in IDENTITY:return ("identity","Source identifier or reported institutional name, not a canonical property or legal owner.","existing_profile")
    if f in GEO:return ("geography","Reported location field; preserve identifier strings, estimated coordinates and geocoding limits.","coordinate" if f in ("Latitude","Longitude") else "existing_profile")
    if "footnote" in f.lower():return ("footnote","Publisher explanation or reporting qualification for the accompanying measure; not a score or adverse event.","footnote")
    if f in ENUMS:
        meaning={"Automatic Sprinkler Systems in All Required Areas":"Source-reported sprinkler coverage of required areas; not a fire inspection verdict.",
                 "Special Focus Status":"Publisher special focus program/candidate status; blank is no listed status in this source, not proof of compliance.",
                 "Hospital Type":"Reported hospital classification; not current operation or service inventory.",
                 "Hospital Ownership":"Reported ownership category, not legal property title.",
                 "Emergency Services":"Reported emergency service availability, not real-time operation.",
                 "Meets criteria for birthing friendly designation":"Reported CMS designation indicator, not a count of obstetric units.",
                 "With a Resident and Family Council":"Reported resident and/or family council type."}[f]
        return ("reported_classification",meaning,"enum")
    if f in NH_FLAGS:return ("reported_flag",NH_FLAGS[f],"yn")
    if f=="Hospital overall rating" or f in NH_RATINGS:return ("clinical_quality_rating","CMS composite/domain quality rating on a 1–5 scale; not a property-risk or current-compliance score.","rating")
    if f.startswith("Chain Average "):return ("chain_quality_context","Source-reported average rating across affiliated group; repeated values are not independent facility ratings.","chain_rating")
    if f in ("Chain Name","Chain ID","Number of Facilities in Chain"):return ("affiliation","CMS reported affiliation grouping or membership count; not verified controlling entity.","count" if f.startswith("Number") else "existing_profile")
    if f in ("Ownership Type","Provider Type"):return ("reported_classification","Provider's reported operator or program classification; not title ownership.","existing_profile")
    if f=="Number of Certified Beds":return ("capacity","Reported federally certified bed count, not current occupancy or licensed total beds.","count")
    if f=="Average Number of Residents per Day":return ("resident_census","Average daily resident census, not point-in-time occupancy; time bases may differ from beds.","decimal")
    if f=="Nursing Case-Mix Index" or f=="Nursing Case-Mix Index Ratio":return ("staffing_adjustment","Resident acuity adjustment index or ratio to national index; not staffing headcount.","decimal")
    if "hours per resident per day" in f.lower():
        prefix="Case-mix adjusted" if f.startswith("Adjusted ") else "Case-mix reference" if f.startswith("Case-Mix ") else "Reported"
        return ("staffing_hours",prefix+" staff hours per resident per day for the named staff group/period; not headcount, FTE or an independent additive component.","decimal")
    if "turnover" in f.lower():return ("staffing_turnover","Source-reported annual turnover percentage for the named nursing staff population.","percentage")
    if f=="Number of administrators who have left the nursing home":return ("staffing_turnover","Reported administrators departing during the defined annual interval; not total staff.","count")
    if f.startswith("Rating Cycle") or f=="Total Weighted Health Survey Score":
        if f.endswith("Date"):return ("inspection_history","Reported standard survey date for the named rating cycle; not a live inspection.","date")
        if f.endswith("Score"):return ("inspection_score","CMS survey severity/revisit scoring for named cycle; not the number of violations or a property-risk score.","decimal")
        if "Number of" in f:return ("inspection_history","Reported count for named inspection type and rating cycle; windows and flags may overlap.","count")
    if f=="Number of Citations from Infection Control Inspections":return ("inspection_history","Reported infection-control citation count over publisher's three-year interval; not current infection count.","count")
    if f in ("Number of Fines","Number of Payment Denials","Total Number of Penalties"):return ("penalty_history","Publisher historical count of named enforcement category; not current outstanding penalty.","count")
    if f=="Total Amount of Fines in Dollars":return ("penalty_history","Reported historical fine amount in USD; not outstanding debt or current liability.","decimal")
    if f in ("Date First Approved to Provide Medicare and Medicaid Services","Processing Date"):return ("program_or_release_date","Reported program first-approval or file processing date, not proof of current operation.","date")
    if f.endswith("Group Measure Count"):return ("clinical_quality_coverage","Number of measures in named overall-star quality group; not count of facilities or violations.","count")
    if f.startswith("Count of "):return ("clinical_quality_coverage","Reported count of applicable or comparison-classified measures in named clinical group; not patient or event count.","count")
    raise ValueError("Unreviewed field: "+source+"/"+f)
def marker(v):
    return MISSING.get(v.strip().casefold())
def decimal(v):
    s=v.strip();m=marker(s)
    if m is not None:return m,None
    if len(s)>28 or not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?",s):return "unrecognized",None
    return "numeric",Decimal(s)
def number_state(v,kind):
    s,n=decimal(v)
    if n is None:return s
    if n<0:return "negative"
    if kind in ("count","rating") and n!=n.to_integral_value():return "noninteger"
    if kind in ("rating","chain_rating") and not 1<=n<=5:return "outside_1_5"
    if kind=="percentage" and n>100:return "above_100"
    if kind=="rating":return "rating_"+str(int(n))
    return "zero" if n==0 else "positive"
def parsed_date(v):
    s=v.strip();m=marker(s)
    if m is not None:return m,None
    def make(y,m,d):
        try:return date(int(y),int(m),int(d))
        except ValueError:return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}",s):d=make(*s.split("-"));return ("iso",d) if d else ("invalid_date",None)
    if re.fullmatch(r"\d{8}",s):d=make(s[:4],s[4:6],s[6:]);return ("compact",d) if d else ("invalid_date",None)
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}",s):
        a,b,y=s.split("/");ds={d for d in (make(y,a,b),make(y,b,a)) if d}
        if len(ds)==1:return "unambiguous_slash",ds.pop()
        return ("ambiguous_slash" if ds else "invalid_date"),None
    return "unrecognized_format",None
def footnote(v,source):
    s=v.strip();m=marker(s)
    if m is not None:return m
    if len(s)>30 or not re.fullmatch(r"\d{1,2}(?:\s*[,;]\s*\d{1,2})*",s):return "unrecognized"
    parts=re.split(r"\s*[,;]\s*",s)
    if source=="nursing" and not set(parts)<=NH_FOOTNOTES:return "unknown_numeric_code"
    return "code_"+",".join(parts)
def classify(v,kind,f,source):
    if kind=="enum":
        # Known publisher labels first; explicit Data Not Available remains a distinct source value.
        labels={x.casefold():x for x in ENUMS[f]};s=v.strip().casefold()
        return labels[s] if s in labels else marker(v) or "unrecognized"
    if kind=="yn":return {"Y":"Y","N":"N"}.get(v.strip(),marker(v) or "unrecognized")
    if kind=="footnote":return footnote(v,source)
    if kind=="date":return parsed_date(v)[0]
    if kind in ("count","rating","chain_rating","percentage","decimal"):return number_state(v,kind)
    if kind=="coordinate":
        state,x=decimal(v)
        if x is None:return state
        return "in_range" if abs(x)<=(90 if f=="Latitude" else 180) else "outside_coordinate_range"
    return "blank" if not v.strip() else "present"
def valid_count(row,f):
    s,n=decimal(row[f]);return n if n is not None and n>=0 and n==n.to_integral_value() else None
def arithmetic(row,total,parts,integer=False):
    fields=[total]+list(parts);values=[]
    for f in fields:
        s,n=decimal(row[f])
        if n is None or n<0 or integer and n!=n.to_integral_value():return "not_comparable"
        values.append(n)
    delta=values[0]-sum(values[1:])
    if delta==0:return "equal"
    # Exact counts must agree. For decimal quantities, rounding uncertainty
    # is bounded by half of each displayed decimal unit.
    tolerance=sum(Decimal(10)**v.as_tuple().exponent/2 for v in values)
    if not integer and abs(delta)<=tolerance:return "within_display_precision"
    return "reported_total_above_components" if delta>0 else "reported_total_below_components"
def relation(row,a,b):
    sa,x=decimal(row[a]);sb,y=decimal(row[b])
    if x is None or y is None:return "not_comparable"
    return "equal" if x==y else "first_above_second" if x>y else "first_below_second"
def audit(source,path,pin,header,prior):
    expected=[f["field"] for f in header["fields"]]
    need(header["source_sha256"]==prior["source_sha256"]==pin["sha256"] and [f["field"] for f in prior["fields"]]==expected,"header/profile lineage mismatch")
    catalog=[]
    for i,(f,p) in enumerate(zip(expected,prior["fields"]),1):
        category,meaning,kind=semantic(source,f)
        status="publisher_schema_and_methodology_reviewed"
        if source=="nursing" and f in ("High Performing Icon","Rating Cycle 1 Standard Survey Footnote","Rating Cycle 2 Standard Survey Footnote"):
            status="publisher_text_only_revision_disagreement"
        catalog.append({"ordinal":i,"field":f,"category":category,"meaning":meaning,"value_kind":kind,
            "semantic_status":status,"publisher_dictionary":DOCS[source],"prior_profile_status":p["profile_status"],
            "prior_value_states":p.get("states",p.get("presence")),"application_approval":"no_new_row_level_publication"})
    distributions={f["field"]:Counter() for f in catalog};joints=defaultdict(Counter);by_rating=defaultdict(Counter);n=0
    verify_raw(path,pin)
    with path.open(encoding="utf-8-sig",newline="") as stream:
        reader=csv.DictReader(stream);need(reader.fieldnames==expected,"exact raw header mismatch")
        for row in reader:
            need(None not in row and all(v is not None for v in row.values()),"malformed source row");n+=1
            states={}
            for item in catalog:
                f=item["field"];states[f]=classify(row[f],item["value_kind"],f,source);distributions[f][states[f]]+=1
            if source=="hospital":
                rating=states["Hospital overall rating"]
                by_rating[rating][states["Hospital overall rating footnote"]]+=1
                for g,limit in GROUPS.items():
                    total=g+" Group Measure Count";facility="Count of Facility "+g+" Measures"
                    a,b=valid_count(row,total),valid_count(row,facility)
                    joints[g+"_group_size"][("expected" if a==limit else "other_numeric" if a is not None else "unknown")]+=1
                    joints[g+"_facility_count_vs_group"]["not_comparable" if a is None or b is None else "within_group" if b<=a else "above_group"]+=1
                    if g in ("MORT","Safety","READM"):
                        parts=tuple("Count of "+g+" Measures "+v for v in ("Better","No Different","Worse"))
                        joints[g+"_comparison_count_arithmetic"][arithmetic(row,facility,parts,True)]+=1
                    joints[g+"_availability_vs_footnote"][states[facility]+"/"+("footnote_blank" if states[g+" Group Footnote"]=="blank" else "footnote_present")]+=1
            else:
                for rating in NH_RATINGS:
                    joints[rating+"_vs_footnote"][states[rating]+"/"+states[rating+" Footnote"]]+=1
                joints["overall_rating_vs_special_focus"][states["Overall Rating"]+"/"+states["Special Focus Status"]]+=1
                joints["resident_census_vs_certified_beds"][relation(row,"Average Number of Residents per Day","Number of Certified Beds")]+=1
                joints["penalty_component_arithmetic"][arithmetic(row,"Total Number of Penalties",("Number of Fines","Number of Payment Denials"),True)]+=1
                for prefix in ("Reported","Case-Mix","Adjusted"):
                    total=prefix+" Total Nurse Staffing Hours per Resident per Day"
                    parts=tuple(prefix+" "+g+" Staffing Hours per Resident per Day" for g in ("Nurse Aide","LPN","RN"))
                    joints[prefix+"_staffing_arithmetic"][arithmetic(row,total,parts)]+=1
                joints["reported_licensed_staffing_arithmetic"][arithmetic(row,"Reported Licensed Staffing Hours per Resident per Day",("Reported LPN Staffing Hours per Resident per Day","Reported RN Staffing Hours per Resident per Day"))]+=1
                for cycle in ("1","2/3"):
                    prefix="Rating Cycle "+cycle+" "
                    joints["cycle_"+cycle+"_score_arithmetic"][arithmetic(row,prefix+"Total Health Score",(prefix+"Health Deficiency Score",prefix+"Health Revisit Score"))]+=1
                d1,d2,proc=[parsed_date(row[f])[1] for f in ("Rating Cycle 1 Standard Survey Health Date","Rating Cycle 2 Standard Health Survey Date","Processing Date")]
                joints["survey_cycle_date_order"]["not_comparable" if d1 is None or d2 is None else "cycle1_on_or_after_cycle2" if d1>=d2 else "cycle1_before_cycle2"]+=1
                if d1 is not None and proc is not None:
                    try:threshold=proc.replace(year=proc.year-2)
                    except ValueError:threshold=proc.replace(year=proc.year-2,day=28)
                    age="survey_before_two_year_boundary" if d1<threshold else "survey_on_or_after_boundary"
                    if d1>proc:age="survey_after_processing_date"
                else:age="not_comparable"
                joints["survey_recency_vs_reported_flag"][age+"/"+states["Most Recent Health Inspection More Than 2 Years Ago"]]+=1
                joints["coordinate_pair_vs_geocoding_footnote"][states["Latitude"]+"/"+states["Longitude"]+"/"+states["Geocoding Footnote"]]+=1
    verify_raw(path,pin);need(n==pin["input_rows"]==pin["stored_rows"],"source rows mismatch")
    for c in (*distributions.values(),*joints.values()):need(sum(c.values())==n,"aggregate count reconciliation")
    if source=="hospital":need(sum(sum(c.values()) for c in by_rating.values())==n,"rating-footnote reconciliation")
    return {"source":source,"source_sha256":pin["sha256"],"period":pin["release"],"rows":n,"columns":len(catalog),
      "catalog":catalog,"distributions":{f:dict(c) for f,c in distributions.items()},"cross_checks":{k:dict(c) for k,c in joints.items()},
      "hospital_rating_footnote_joint":{k:dict(c) for k,c in by_rating.items()},
      "documentation":{"dictionary":DOCS[source],"visual_pages_reviewed":[20,21] if source=="hospital" else [8,9,10,11,12,25],
       "revision_limit":"Extracted text states October 2026; hospital image footer April 2026 and nursing image footer June/May 2026. New nursing fields and footnote 29 have text/revision-table support, not agreement with rendered older pages."},
      "limitations":["Source snapshots, not live operations, verified physical sites, property risk, or purchase intent.","No new individual rows, addresses, contact values, exact coordinates or dates published.","Clinical ratings are distinct from physical infrastructure, current compliance and safety risk. Counts and staff-hours cannot be summed across overlapping components. Arithmetic checks are diagnostics, not proven errors.","Footnote codes are source scoped. Hospital numeric tokens remain literal; nursing known code domain includes text-only revision 29. Blank is not zero."]}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);p.add_argument("--raw-dir",type=Path);p.add_argument("--download",action="store_true");a=p.parse_args();need(not a.output.exists(),"new output required")
    pins={s["key"]:s for s in read(LOCK)["sources"]};headers={s["source"]:s for s in read(HEADERS)["sources"]};profiles={s["source"]:s for s in read(PROFILES)["sources"]}
    results=[]
    with tempfile.TemporaryDirectory(prefix="care-compare-semantic-") as d:
        for key in SOURCES:
            path=materialize(pins[key],a.raw_dir,Path(d),a.download);results.append(audit(key,path,pins[key],headers[key],profiles[key]))
    need(sum(r["columns"] for r in results)==140 and sum(r["rows"] for r in results)==20121,"expected combined coverage mismatch")
    result={"format_version":1,"as_of":"2026-11-26","sources":results,"field_count":140,"source_rows":20121}
    with a.output.open("x",encoding="utf-8") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    for r in results:
        print("CC_SEMANTIC_SUMMARY",json.dumps({k:v for k,v in r.items() if k!="catalog"},separators=(",",":"),sort_keys=True),flush=True)
        for f in r["catalog"]:print("CC_SEMANTIC_FIELD",r["source"],json.dumps(f,separators=(",",":"),sort_keys=True),flush=True)
if __name__=="__main__":main()
