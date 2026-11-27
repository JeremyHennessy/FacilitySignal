'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {reconcile,load}=require('../scripts/reconcile_storage_coverage.js');
const root=require('node:path').resolve(__dirname,'..');
const input=load(root);
const output=reconcile(input);
const clone=x=>JSON.parse(JSON.stringify(x));
test('pinned full register, layers and receipt counts',()=>{assert.equal(output.register_entries,176);assert.equal(output.additional_national_entries,6);assert.equal(output.archive_totals.payload_files,216);assert.equal(output.archive_totals.source_observations,117921992);assert.equal(output.archive_totals.derived_enrollment_corroboration_rows,40709);assert.equal(output.archive_totals.payload_bytes,10931163793);});
test('ownership and restricted screening states',()=>{assert.equal(output.sources.find(x=>x.id==='FS-049').evidence[0].observations,21734);assert.equal(output.sources.find(x=>x.id==='FS-050').evidence[0].observations,18763);assert.equal(output.sources.find(x=>x.id==='FS-009').evidence.length,0);assert.equal(output.sources.find(x=>x.id==='FS-060').qualification,'bounded_award_page_qualification');});
for(const [name,mutate] of [['duplicate receipt',d=>d.inventory.receipts.push(d.inventory.receipts[0])],['extension drift',d=>d.extension.source_log_results['FS-036'].rows++],['total drift',d=>d.inventory.totals.payload_bytes++],['unknown overlay',d=>d.overlay.sources['FS-999']={keys:['nppes-monthly']}],['unmapped core',d=>d.coverage.additional_qualified_datasets[0].adapter='nonexistent']])test(name,()=>{const d=clone(input);mutate(d);assert.throws(()=>reconcile(d));});

test('FS-039 private scope and persisted reconciliation match',()=>{const row=output.sources.find(x=>x.id==='FS-039');assert.equal(row.qualification,'private_organizational_projection_qualified');assert.equal(row.storage,'private_archive_partial');assert.equal(row.evidence[0].observations,71270);assert.equal(output.register_storage_counts.no_pinned_source_projection,129);const {baseline_commit,input_git_blob_shas,offline_validation_checks,...saved}=require('../docs/storage_coverage_reconciliation_20261126.json');assert.deepEqual(output,saved);});

test('FS-041 structural screening does not imply private archive retention',()=>{const row=output.sources.find(x=>x.id==='FS-041');assert.equal(row.historical_status,'aggregate_screening_qualified');assert.equal(row.qualification,'aggregate_screening_qualified');assert.equal(row.storage,'no_pinned_source_projection');assert.deepEqual(row.evidence,[]);assert.equal(output.discovery_only_entries,123);});

test('FS-042 separate quality grains are not a private archive',()=>{const row=output.sources.find(x=>x.id==='FS-042');assert.equal(row.qualification,'aggregate_screening_qualified');assert.equal(row.storage,'no_pinned_source_projection');assert.deepEqual(row.evidence,[]);});
