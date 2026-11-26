// Reconcile immutable repository evidence; no network or private data reads.
'use strict';
const fs=require('node:fs');
const path=require('node:path');
const paths={
  "register": "research/facilitysignal_source_register_v0.2.json",
  "coverage": "research/coverage_status.json",
  "inventory": "research/azure_archive_inventory_20261126.json",
  "overlay": "research/private_source_register_receipt_map_20261126.json",
  "national": "research/snapshot_release_20261125.json",
  "expanded": "research/expanded_source_lock_20261126.json",
  "extension": "research/azure_extension_recovery_pin_20261126.json",
  "procurement": "research/procurement_awards_audit_20261126.json"
};
function reconcile(d){
 const check=(v,m)=>{if(!v)throw Error(m);};
 const sum=(arr,f)=>arr.reduce((n,x)=>n+f(x),0), unique=(arr,k)=>{const m=new Map();for(const x of arr){const v=k(x);check(!m.has(v),"duplicate "+v);m.set(v,x);}return m;};
 const digest=s=>typeof s==="string"&&/^[a-f0-9]{64}$/.test(s);
 const reg=unique(d.register.sources,x=>x.id),hist=unique(d.coverage.sources,x=>x.id),nat=unique(d.national.sources,x=>x.key),exp=unique(d.expanded.expanded_sources,x=>x.source_id);
 check(reg.size===hist.size&&[...reg.keys()].every(k=>hist.has(k)),"register/coverage membership mismatch");
 check(d.inventory.layers.length===2&&d.inventory.layers[0].key==="national"&&d.inventory.layers[1].key==="extension","unexpected archive layers");
 const [nl,el]=d.inventory.layers;
 const recs=d.inventory.receipts, byVersion=unique(recs,x=>x.key+"/"+x.source_sha256);
 for(const x of recs){check(digest(x.source_sha256)&&x.files.length===2&&new Set(x.files.map(f=>f.path)).size===2&&x.files.every(f=>digest(f.sha256)&&Number.isSafeInteger(f.bytes)&&f.bytes>0),"invalid receipt "+x.key);check(["publisher","supplemental_numeric","aggregate","derived","institutional_fields","evidence_bundle","enrollment_corroboration"].includes(x.kind),"unknown archive grain");}
 const kind=k=>recs.filter(x=>x.kind===k),t=d.inventory.totals;
 const derivedTotals={publisher_releases:nl.source_releases+el.source_releases+kind("publisher").length,source_observations:nl.observations+el.observations+sum([...kind("publisher"),...kind("supplemental_numeric")],x=>x.observations),supplemental_numeric_archives:kind("supplemental_numeric").length,supplemental_numeric_observations:sum(kind("supplemental_numeric"),x=>x.observations),derived_candidate_observations:sum(kind("derived"),x=>x.observations),aggregate_evidence_releases:kind("aggregate").length,aggregate_source_rows_screened:sum(kind("aggregate"),x=>x.screened_observations),payload_files:nl.files+el.files+sum(recs,x=>x.files.length),payload_bytes:nl.payload_bytes+el.payload_bytes+sum(recs,x=>sum(x.files,f=>f.bytes)),derived_institutional_observations:sum(kind("institutional_fields"),x=>x.observations),repository_data_evidence_files:sum(kind("evidence_bundle"),x=>x.tracked_data_file_count),repository_supplemental_data_files:sum(kind("evidence_bundle"),x=>x.supplemental_file_count)};
 if(kind("enrollment_corroboration").length)derivedTotals.derived_enrollment_corroboration_rows=sum(kind("enrollment_corroboration"),x=>x.observations);
 check(Object.keys(t).length===Object.keys(derivedTotals).length&&Object.entries(derivedTotals).every(([k,v])=>Number.isSafeInteger(v)&&v===t[k]),"archive total mismatch");
 check(nat.size===nl.source_releases&&sum([...nat.values()],x=>x.stored_rows)===nl.observations&&d.national.source_records_total===nl.observations,"national source lock mismatch");
 const extRows=[...exp.values()].filter(x=>x.scope==="ephemeral_projection");
 check(extRows.length===el.source_releases&&sum(extRows,x=>x.qualified_rows)===el.observations,"extension source lock mismatch");
 check(d.extension.release===el.release&&d.extension.base_release===nl.release,"extension release mismatch");
 for(const x of extRows){const p=d.extension.source_log_results[x.source_id];if(x.source_id==="FS-011"){check(!p,"FDA evidence scope changed; review mapping");continue;}check(p&&p.source_sha256===x.sha256&&p.rows===x.qualified_rows,"extension per-source mismatch "+x.source_id);}
 check(Object.keys(d.extension.source_log_results).length===extRows.length-1,"extension pin membership");
 const referenced=new Set(),usedNational=new Set(),usedExtension=new Set();
 const addReceipt=x=>{referenced.add(x.key+"/"+x.source_sha256);return {key:x.key,source_sha256:x.source_sha256,kind:x.kind,observations:x.observations,...(x.kind==="aggregate"?{screened_observations:x.screened_observations}:{}),receipt_run:x.run};};
 const core=(x,l,rows)=>({key:x.key,source_sha256:x.sha256,kind:"qualified_private_projection",observations:rows,layer:l.key,receipt_run:l.run});
 const overlays={...d.overlay.sources,"FS-049":{status:"private_archive_partial",keys:["hha-organizational-ownership"],limit:"Organizational role rows only; excludes individual owners; no legal title or current operational control."},"FS-050":{status:"private_archive_partial",keys:["hospice-organizational-ownership"],limit:"Organizational role rows only; excludes individual owners; no legal title or current operational control."}};
 for(const id of Object.keys(overlays))check(reg.has(id),"unknown overlay source "+id);
 const sources=[...reg.values()].map(s=>{
   const h=hist.get(s.id),e=exp.get(s.id),o=overlays[s.id],n=nat.get(h.adapter);let storage="no_pinned_source_projection",evidence=[],limit=null,qualification=h.status;
   if(n&&h.status==="snapshot_qualified"){check(!usedNational.has(n.key),"duplicate national mapping");usedNational.add(n.key);storage="national_private_projection";evidence=[core(n,nl,n.stored_rows)];limit="Pinned source-native projection; not raw original or public row clearance.";}
   if(e&&e.scope==="ephemeral_projection"){check(!evidence.length,"overlapping core mapping");usedExtension.add(e.source_id);storage="extension_private_projection";evidence=[core(e,el,e.qualified_rows)];limit="Pinned private extension; prior ephemeral label is historical.";}
   if(o){check(!evidence.length,"overlay conflicts with core");const matched=recs.filter(x=>(o.keys||[]).includes(x.key)||(o.prefix&&x.key.startsWith(o.prefix)));check(matched.length&&(!o.keys||o.keys.every(k=>matched.some(x=>x.key===k))),"unresolved archive overlay "+s.id);storage=o.status;evidence=matched.map(addReceipt);limit=o.limit;}
   if(e&&e.scope==="aggregate_screening"){check(!evidence.length,"aggregate-only scope conflict");storage="aggregate_qualification_only";limit="Aggregate screening evidence; no source-row archive. Protected locations excluded.";}
   if(s.id==="FS-060"){check(d.procurement.audit.sample_rows===100&&d.procurement.audit.retained_row_level_records===0&&digest(d.procurement.audit.response_sha256),"procurement scope drift");qualification="bounded_award_page_qualification";limit="100-row diagnostic page; no retained award rows, site linkage, or active opportunity. No source archive pin.";}
   const blocked=h.status.startsWith("blocked_");
   return {id:s.id,source:s.source,priority:s.priority,historical_status:h.status,qualification,storage,evidence,limit,blocked,raw_original_retention:"not_established_by_this_ledger",public_row_redistribution:"not_granted_by_private_archive"};
 });
 const additional=d.coverage.additional_qualified_datasets.map(h=>{const n=nat.get(h.adapter);check(n&&!usedNational.has(n.key),"additional national source mapping");usedNational.add(n.key);return {key:n.key,historical_status:h.status,storage:"national_private_projection",evidence:[core(n,nl,n.stored_rows)]};});
 check(usedNational.size===nat.size&&usedExtension.size===extRows.length,"unmapped core archive source");
 const supplemental=recs.filter(x=>!referenced.has(x.key+"/"+x.source_sha256)).map(x=>({storage:x.kind==="publisher"?"additional_private_publisher_projection":x.kind,evidence:addReceipt(x)}));
 check(referenced.size===byVersion.size,"supplemental coverage mismatch");
 const stateCounts={};for(const s of sources)stateCounts[s.storage]=(stateCounts[s.storage]||0)+1;
 const discoveryOnly=sources.filter(x=>x.historical_status==="discovered_not_tested"&&x.evidence.length===0&&x.qualification==="discovered_not_tested").length;
 return {format_version:1,scope:"Reconciliation of pinned repository evidence, not fresh Azure access or publisher/reuse approval. Register entries and receipt references overlap; never sum source-entry observations. No raw retention or public approval inferred.",archive_evidence_mode:"historical_metadata_inventory_and_prior_upload_sha256",archive_totals:derivedTotals,register_entries:sources.length,additional_national_entries:additional.length,register_storage_counts:stateCounts,discovery_only_entries:discoveryOnly,sources,additional_national_sources:additional,additional_or_derived_receipts:supplemental,public_and_research_evidence:{pinned_commit:d.inventory.evidence_commit,tracked_data_json_files:t.repository_data_evidence_files,supplemental_json_files:t.repository_supplemental_data_files,extension_pack_byte_parity:d.extension.app_parity,limit:"Historical pack parity and pinned evidence inventory; not an ordinary-live browser check or new publication."}};
}
function load(root){return Object.fromEntries(Object.entries(paths).map(([k,p])=>[k,JSON.parse(fs.readFileSync(path.join(root,p),'utf8'))]));}
if(require.main===module)process.stdout.write(JSON.stringify(reconcile(load(path.resolve(__dirname,'..'))),null,2)+'\n');
module.exports={reconcile,load};
