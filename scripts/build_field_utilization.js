// Deterministic evidence-based field routing; no data publication.
const fs=require("node:fs"),path=require("node:path");
const ROOT=path.resolve(__dirname,"..");
const paths={
  "index": "research/national_data_understanding_index_20261126.json",
  "pecos": "research/pecos_field_semantic_crosswalk_20261126.json",
  "iqies": "research/iqies_semantic_application_crosswalk_20261126.json",
  "qies": "research/qies_hospital_infrastructure_audit_20261126.json",
  "clia": "research/clia_certificate_semantic_audit_20261126.json",
  "infrastructure": "research/care_compare_infrastructure_qualification_20261126.json",
  "clinical": "research/clinical_measure_quality_qualification_20261126.json"
};
function build(d,paths) {
 const need=(ok,msg)=>{if(!ok)throw Error(msg)};
 const counts={},surfaces={},sources=[],inc=(x,k)=>x[k]=(x[k]||0)+1;
 const indexed=new Map(d.index.sources.map(s=>[s.source,s]));
 const pecos=new Map(d.pecos.sources.map(s=>[s.source,s]));
 const iq=new Map(d.iqies.fields.map(f=>[f.field,f])), cl=new Map(d.clia.catalog.map(f=>[f.field,f]));
 const priorCategory={source_identity:"directory_identity",geography:"geography",organization_relationship:"organization_context",capacity:"reported_capacity",workforce:"workforce_context",regulatory_evidence:"historical_regulatory_context",clinical_quality_or_reporting_context:"clinical_reporting_context",service_or_provider_classification:"reported_services",program_and_release_context:"program_and_release",identity_review:"directory_identity",organization_or_contract_review:"organization_context",regulatory_review:"historical_regulatory_context",service_or_lab_review:"reported_services",capacity_review:"reported_capacity",identity:"directory_identity",certification:"program_and_release",administrative:"program_and_release",organization:"organization_context",service_provision:"reported_services",surgical_specialty:"reported_services",dialysis_service:"reported_services",corf_provision:"reported_services",waiver:"historical_regulatory_context",governance_context:"organization_context"};
 const blockedIq=new Set(d.iqies.summary.blocking_semantic_fields);
 need(d.index.sources.length===19 && indexed.size===19,"source scope");
 for(const s of d.index.sources){
   need(s.fields.length===s.columns&&new Set(s.fields.map(f=>f.field)).size===s.columns,"header uniqueness");
   const ps=pecos.get(s.source);
   if(ps)need(ps.source_sha256===s.sha256&&ps.fields.length===s.columns,"PECOS provenance");
   const infra=d.infrastructure.sources[s.source], clinical=d.clinical.sources[s.source];
   for(const a of [infra,clinical].filter(Boolean))need(a.sha256===s.sha256&&a.rows===s.profiled_rows,"audit provenance");
   const fields=[];
   for(let i=0;i<s.fields.length;i++){
     const f=s.fields[i],n=f.ordinal,name=f.field,key=s.source;need(n===i+1,"ordinal");
     let surface=priorCategory[f.category]||"unresolved",basis=[],restricted=f.profile==="presence_only",blocked=false;
     // The original index uses presence_only_profile in some historical entries.
     restricted=restricted||f.profile.includes("presence_only")||f.category==="restricted_or_presence_only";
     if(key==="iqies"){const a=iq.get(name);need(a&&a.ordinal===n,"iQIES coverage");surface=priorCategory[a.category]||"unresolved";restricted=restricted||a.category==="contact";blocked=blockedIq.has(name);basis.push("iqies");}
     if(key==="qies"){
       const a=d.qies.catalog[name];if(a){basis.push("qies");surface=name.endsWith("_SRVC_CD")?"reported_services":d.qies.scope_results.code00_same_state_hospital_candidate.fte[name]?"workforce_context":d.qies.scope_results.code00_same_state_hospital_candidate.counts[name]?"reported_capacity":"program_and_release";}
       if(name===d.qies.blocked_field.field)blocked=true;
     }
     if(key==="clia"){const a=cl.get(name);need(a&&a.ordinal===n,"CLIA coverage");basis.push("clia");if(a.category==="quantity")surface="laboratory_quantity_context";else if(a.category==="date"||a.category==="coded_classification")surface="program_and_release";}
     if(ps){const a=ps.fields[i];need(a.field===name&&a.ordinal===n,"PECOS ordinal");basis.push("pecos");restricted=restricted||["restricted_text","excluded_personal","restricted_address"].includes(a.kind);surface=["address","geography","jurisdiction"].includes(a.kind)?"geography":"organization_context";}
     if(key==="hospital"&&n>=13||key==="home-health"&&n>=16||key==="dialysis"&&(n>=23||n>=4&&n<=6))surface="clinical_reporting_context";
     if(key==="hospital"&&(n===11||n===12))surface="reported_services";
     if(key==="nursing"){
       if(n===13||n===14)surface="resident_census_context";
       if(n>=22&&n<=25||n>=34&&n<=47||n===62||n===63)surface="clinical_reporting_context";
       if(n>=48&&n<=61||n>=64&&n<=73)surface="workforce_context";
       if(n===27||n===28||n===30||n>=74&&n<=97)surface="historical_regulatory_context";
       if(n===33)surface="building_infrastructure";
       if(n===101)surface="geography";
     }
     if(infra&&(Object.hasOwn(infra.literal_counts,name)||key==="dialysis"&&name==="# of Dialysis Stations"))basis.push("infrastructure");
     if(clinical&&(Object.hasOwn(clinical.field_counts,name)||Object.keys(clinical.cross_checks).some(k=>k.startsWith(name+" | "))))basis.push("clinical");
     const mapped=f.existing_projection_20261126_baseline!==null&&f.existing_projection_20261126_baseline!==undefined;
     const disposition=restricted?"restricted_review":f.all_blank?"no_observed_values":blocked?"blocked_semantics":mapped?"prior_mapping_retained":basis.includes("infrastructure")||basis.includes("clinical")||basis.includes("qies")?"targeted_diagnostic_evidence":"semantic_or_use_review_required";
     if(restricted)surface="restricted";else if(f.all_blank)surface="no_observed_values";else if(blocked)surface="unresolved";
     inc(counts,disposition);inc(surfaces,surface);
     fields.push({ordinal:n,field:name,surface,disposition,basis,prior_mapping:mapped?f.existing_projection_20261126_baseline:null});
   }
   sources.push({source:s.source,release:s.release,sha256:s.sha256,columns:s.columns,fields});
 }
 need(sources.reduce((a,s)=>a+s.fields.length,0)===1433,"national field count");
 need(Object.values(counts).reduce((a,b)=>a+b,0)===1433,"disposition count");
 return {format_version:1,as_of:"2026-11-26",scope:"Exhaustive routing plan from existing evidence, not complete semantic qualification or a new public projection. Each field is assigned one provisional destination and a review disposition. Existing mapping is adapter evidence, not live use.",evidence:paths,policy:{clinical_reporting_context:"Clinical quality and reporting context only; never a building/environmental score by default.",resident_census_context:"Reported resident census; not licensed or installed capacity.",workforce_context:"Separate raw/adjusted FTE, hours and turnover. No unqualified sums.",reported_capacity:"Source-specific unit, applicability and outlier review before aggregation.",building_infrastructure:"Snapshot-reported infrastructure, not verified inspection or current condition.",organization_context:"Separate legal/operational roles, source-family IDs and history; not legal title.",reported_services:"Source-reported provision, not installed equipment, vendor contract or procurement intent.",historical_regulatory_context:"Preserve survey date/type, correction state and reporting limits; no current violation inference.",laboratory_quantity_context:"Do not add overlapping test volumes or equate them with analyzer counts.",restricted:"No new row-level exposure.",no_observed_values:"Do not coerce missing to zero.",unresolved:"No promotion until exact meaning and applicable domain are qualified."},counts,surfaces,sources};
}
const d=Object.fromEntries(Object.entries(paths).map(([k,p])=>[k,JSON.parse(fs.readFileSync(path.join(ROOT,p),"utf8"))]));
const actual=JSON.stringify(build(d,paths),null,2)+"\n";
const target=path.join(ROOT,"research/field_utilization_20261126.json");
if(process.argv.includes("--check")){if(fs.readFileSync(target,"utf8")!==actual)throw Error("field routing drift");console.log("FIELD_ROUTING_VERIFIED",JSON.stringify(JSON.parse(actual).counts));}else fs.writeFileSync(target,actual);
