# FacilitySignal — data understanding and utilization audit
**Date:** 2026-11-26 | **Reviewed main:** `5ed5eeceae8c258c1d7c1d780162c274603060cd`  
**Status:** Initial documentation and schema reconciliation; full raw-value semantic review and profiling remain open. This is a documentation-only workstream, not a new production release or approval of additional public redistribution.

## Mission and operating priority
Prioritize understanding, documenting, profiling, and safely using existing FacilitySignal data over adding further broad source families. Continue necessary freshness, integrity and recovery work. Never turn an unexplained code, missing value, historical survey, certification record, or service flag into a current operational, physical asset, risk, legal ownership, or procurement conclusion. Preserve all current application behavior and approved baselines. Do not change production until the meaning, applicability, observed value domain, grain, lineage and permitted use of the affected field are established.

## Evidence and source boundaries
- [Pinned national release manifest](../research/snapshot_release_20261125.json): 19 datasets, 1,904,060 retained source records. The six PECOS files deliberately exclude 326,781 individual owner rows. Those are not source ingestion failures.
- [Current coverage ledger](../research/coverage_status.json): 176 original source entries, including 13 snapshot-qualified entries, 159 discovered/not tested, one publisher documentation reviewed, one ephemeral projection qualified, one access blocked, one key-format review blocked. Six additional qualified dataset entries are tracked separately; a source-family entry is not necessarily a single file.
- [National source recovery](NATIONAL_RECOVERY_AND_POS_EVIDENCE_20261125.md), [date normalization checkpoint](SOURCE_EVIDENCE_20261126.md), and [public intelligence workspace](PUBLIC_INTELLIGENCE_20261126.md) establish historical qualification scope. No full current national database or raw originals are available in the reviewed repository. The last full date-normalized snapshot was 906,149,888 bytes; historical execution and recovery evidence do not prove current durable storage.
- [Column catalog](../research/data_column_catalog_20261126.json) records the pinned source digests, exact POS headers, existing adapter-selected fields, documented meanings or limitations, and current projection/publication status. The catalog has no individual/provider row values and is not a complete publisher dictionary.
- [Actual public directory profile](../research/public_projection_field_profile_20261126.json) contains fresh aggregate profiles for successfully read files, plus explicit failures for the five truncated connector reads. It is not a profile of the original CMS data. The existing public Pages site is a narrowly approved static projection, not the national database.

## Source-by-source intelligence and grain

| Source | Retained records | Grain / principal intelligence | Key caution |
|---|---:|---|---|
| Hospital Care Compare | 5,435 | Provider directory; hospital subtype, reported ownership and geography | CCN is not a building or legal owner |
| Nursing Care Compare | 14,686 | Provider directory; certified beds, reported chain/ownership | Capacity is certified beds, not occupancy |
| Dialysis Care Compare | 7,471 | Provider directory; reported dialysis station capacity | Not installed machines or water treatment assets |
| Home health Care Compare | 12,409 | Agency directory and location | Office address is not patient care location |
| Hospice Care Compare | 6,470 | Provider directory | May serve patients in multiple settings |
| Rehabilitation Care Compare | 1,222 | Inpatient rehabilitation provider directory | May be a distinct unit within another facility |
| Long-term hospital Care Compare | 311 | Long-term hospital provider directory | May share a physical campus |
| Nursing health citations | 418,682 | Historical source citation row; survey, tag, severity, correction evidence | Not distinct incidents or current outstanding violations |
| Nursing fire citations | 200,387 | Historical fire/life-safety/preparedness source citation row | Includes different tag types and correction states |
| QIES POS | 13,598 | Registry row; provider types, certification and service provision context | Historical 2023 dictionary labels remain provisional for Q3 2026 |
| iQIES POS | 100,334 | Registry row; certification, surgery/dialysis capability and status | Provider-type applicability, missing states and date ambiguity matter |
| CLIA POS | 686,058 | Laboratory registry row; certification identity and potential lab classification | Not a count of active labs, installed analyzers or distinct properties |
| QCOR hospital surveys | 284,391 | Hospital survey workbook row, including tag, memo and no-tag-reported rows | No-tag row is not proof of a clean inspection; status unknown |
| Hospital PECOS enrollment | 9,120 | Enrollment identity, PAC ID, CCN, NPI and organization context | Enrollment does not establish physical site |
| Hospital PECOS organizational roles | 22,735 | Source organization role row | Role is not automatically ownership or control |
| Hospital PECOS CHOW | 779 | Buyer/seller ownership-change record | Not proof of real-estate transfer |
| SNF PECOS enrollment | 14,401 | Enrollment identity and organization context | Preserve program and source family |
| SNF PECOS organizational roles | 100,231 | Source organization role row | No automatic beneficial-owner inference |
| SNF PECOS CHOW | 5,340 | Buyer/seller ownership-change record | Distinguish effective date from current ownership |
| **Total** | **1,904,060** | **Retained source records** | **Not unique sites or active healthcare facilities** |

FDA MQSA: 9,146 separately qualified ephemeral projection rows; no individual row publication, stable publisher identifier or inclusion in national total. EPA SDWA: 434,757 input rows, 3,287 unresolved identifier formats; blocked strict gate, no retained source rows or confirmed site matches. CMS citation dictionary: 643 lookup rows, separate aggregate qualification. Preserve each evidence boundary.

## Complete registry header reconciliation — first pass

| Registry | Exact raw columns | Base projection source columns | Additional projection source columns | Distinct projected columns | Neither projection |
|---|---:|---:|---:|---:|---:|
| QIES | 473 | 11 | 12 | 23 | 450 |
| iQIES | 186 | 11 | 13 | 22 | 164 |
| CLIA | 103 | 11 | 0 | 11 | 92 |
| **Total** | **762** | **33** | **25** | **56** | **706** |

Two iQIES columns overlap base and additional projections. These are counts of exact source fields, not observations or usable commercial signals. QIES has 12 provision-code fields with historical-reference definitions; iQIES has 13 additional-projection fields with bounded publisher-dictionary evidence (8 capability fields, 5 status fields). The remaining 31 base-only fields have adapter-level mapping but do not have complete publisher semantic qualification. The 706 fields outside current projections require substantive individual review. Some will be administrative, redundant, personal/sensitive, empty or not applicable; do not treat all as additional business intelligence. For Care Compare and PECOS the current catalog documents adapter aliases/selected columns, not the full original release headers. The QCOR workbook has 18 exact headers; only 14 structured columns are projected, four narrative columns are deliberately excluded.

### Existing qualified examples

| Field | Meaning | Scope and permitted interpretation |
|---|---|---|
| `oprtg_room_cnt` | Operating room count | ASC source count; 8,036 reported numeric, 452 unavailable, 4 unrecognized in qualified field distribution. Not installed equipment count. |
| `procedure_room_cnt` | Procedure room count | ASC source count; not operating room count |
| `dntl_srgry_sw` | Dental surgical specialty indicator | ASC yes/no, 651 affirmative observations, not a count of dental chairs |
| `endscpy_srgry_sw` | Endoscopy surgical specialty indicator | ASC yes/no, 2,400 affirmative observations |
| `dlys_stn_cnt` | Number of approved in-center dialysis stations | ESRD source count, not active machines or water system capacity |
| `hmdlys_srvc_sw` | Current in-center hemodialysis indicator | ESRD, source-reported service |
| `prtnl_dlys_srvc_sw` | Current in-center peritoneal dialysis indicator | ESRD, source-reported service |
| `home_trng_sprt_only_srvc_sw` | Onsite home training indicator | ESRD, distinguish training from in-center treatment |
| `pgm_trmntn_cd` | Program termination code | Official M2 domain, code 00 relates only to program status |
| `fed_crtfctn_stus_id` / `fed_crtfctn_stus_name` | Federal certification status ID/name | Source-native fields; no broad operational inference |
| `cmplnc_stus_cd` | Survey compliance status | Not present-day overall compliance |
| `trmntn_exprtn_dt` | Termination or expiration date | Reported, ambiguous, unavailable, blank and unknown separately |
| `CT_SCAN_SRVC_CD`, `MGNTC_RSNC_IMG_SRVC_CD`, `PET_SCAN_SRVC_CD` | CT, MRI, PET provision codes | QIES hospital scope; literal 0/1/2/3 with provisional historical labels; no ownership/installation inference |

iQIES dictionary qualification found 185 of 186 exact field names; missing `fed_fundd_fqhc_sw` and duplicate `physn_arngmt_sw` require review. Field presence or dictionary matches alone do not qualify the value domain. The date-normalization audit recorded 15,803 reported, 9,765 ambiguous and 74,766 not available. Preserve those classes.

## Actual current public data read
Four provider files successfully retrieved in full, parsed and reconciled to the committed public manifest: 6,470 hospice, 5,435 hospital, 311 long-term hospital and 1,222 rehabilitation rows (13,438 total). Every provider's projected name, CCN, address, city, state and ZIP is nonblank in these four files. Every capacity value is blank. This is a limitation of the current narrow public projection, not proof that these providers have no beds or infrastructure. Literal normalized address/city/state/ZIP tuple counts are 6,464, 5,425, 311 and 1,222 respectively; repeated address text is not proof of common legal ownership or site identity. Five larger public files returned truncated JSON through the connector and were not profiled here. Do not report nine-shard profiling as completed. Re-run the same read-only profile from a checked-out repository, reconcile every shard against its manifest, and record missing, explicit zero, numeric, nonnumeric, range, unit, identifier uniqueness, and aggregate total only where semantically valid. No new raw-source downloads are needed for that public-only step.

## Canonical intelligence design (proposed, not implemented)
Keep independent concepts and source-specific identifiers:
1. **Provider program record**: source, release, CCN/registry ID, type, certification context.
2. **Physical property/campus**: address and geospatial evidence, separate identity; no automatic co-location merge.
3. **Organization**: PAC ID, NPI, source legal/trade names and relationships, role and effective dates.
4. **Capability observation**: type-specific service, capacity count/unit, provision mode, reporting period, availability state and evidence.
5. **Regulatory event and finding**: source, event ID if available, survey date/type, tag/domain/severity, correction state/date, source row provenance.
6. **Certification/status observation**: exact program, code/domain, date and applicability; not general active-operation status.
7. **Research/market signal**: traceable evidence, scope, caveats, confidence and explicit absence of confirmed procurement intent.
8. **Source release and field definition**: exact hash, field ordinal, native code, definition version, permitted use, source data state and application mapping.

Use exact source keys, then candidate links with state/type and address evidence. The previous national run recorded 47,169 candidate pairs, 835 provider rows without candidates and 34,264 same-state/type address-city-ZIP text corroborations. These are evidence counts, not canonical resolved sites. Retain many-to-many links, unmatched rows and conflicts. Use CCN only within an appropriate source/program scope; use PECOS enrollment + PAC ID for the source relationship link, not an inferred deed. No destructive merge or hierarchy promotion without independent validation.

## Required per-field documentation contract
For every original field of every pinned dataset record:
- Source release, hash, exact name, ordinal, dictionary URL/version/page or worksheet row; original spelling and alias history.
- Definition and uncertainty status, table grain, applicability and reporting period, raw and normalized data type, unit and precision.
- All valid code values with publisher evidence; actual aggregate observed value counts, blank/unavailable/not applicable/unknown/explicit zero states, unexpected values.
- Completeness and duplicate measures, cardinality, constraints, dates and ranges where meaningful; explain denominator and coverage; never publish free-text or individual values to demonstrate distributions.
- Current storage destination and transformations; raw availability and recovery proof; derived output lineage; join keys and failure modes.
- Relevance category, user question the field could answer, approved display label, filters/aggregation eligibility, review/reuse permission and publication restrictions.
- Evidence that contradicts the initial interpretation, unresolved anomalies, and independent validation status. Record explicit not-applicable or intentionally excluded reason rather than silently omit fields.

Status progression: exact header inventoried -> publisher definition reviewed -> applicability/domain reconciled -> full raw profile qualified -> normalization/join tested -> reuse reviewed -> application use qualified. A field may instead be blocked, intentionally excluded or not useful. Never advance merely because the field name resembles a familiar concept. Codes and distributions must be release-specific.

## Next execution sequence — prioritize existing data
1. **Finish exact schema inventory** for nine Care Compare and six PECOS sources. Existing selected aliases are not exact full raw headers. Reuse pinned manifests, retained qualification artifacts and publisher dictionary references. For all 19 record source grain, explicit inclusion/exclusion and transformations; include schema drift across releases.
2. **Complete POS semantics**: begin with iQIES 186-field dictionary (exact worksheet location, provider-type applicability, domain and missing-value states; resolve two known anomalies); then all QIES 473 and CLIA 103 fields using current-version documentation and historical-layout differences. Prioritize labs, service provision, imaging, surgery, capacity, certification, life safety, contracted arrangements, accreditation, waivers and provider types, without assuming definitions from abbreviations.
3. **Profile real values**: use available checksum-verified originals or approved offline snapshot. For each CSV/XLSX column stream counts, missing classes, explicit zero, valid/invalid domain, ranges, distinct counts with clear exact/approximate methods, data types and cross-field contradictions. Raw value output restricted; only reviewed safe aggregate code distributions may leave private storage. Reconcile input and stored rows plus deliberate exclusions. If originals are unavailable, record blocker and perform minimal targeted source recovery only when it adds substantive field evidence, not repeated blanket downloads. Never replace approved data during profiling.
4. **Validate relationships**: separately assess provider-to-registry, program-to-property candidate links, organizational roles and CHOW timelines, nursing citation tag/version and correction dates, hospital survey event/tag/memo grain and CLIA site/organization ambiguity. Do not merge merely on address/name or sum historical records into current violations. Preserve unknown and conflicts.
5. **Build application-ready semantic views** only after review: facility overview, type-specific service capabilities, capacity in correct units, compliance timelines, certification history, ownership/portfolio evidence, national coverage/quality inspector and research filters. Map every display field back to definition and source release. Prioritize using known data better instead of adding unsupported features. Existing Pages is approved only for selected projections/aggregate evidence; do not expose full database or new row-level sources until permitted and verified.
6. **Document and qualify each slice**: versioned per-source dictionaries, per-column status ledger, aggregate profile files, field-to-app mapping, test fixtures and independent checks. Track exact counts of inventoried/defined/domain-qualified/profiled/projected/application-qualified/blocked fields. Use deterministic tests for identifiers, null/zero separation, schema changes, units and denominators. Verify actual browser data and regressions before any UI promotion.

## Application questions and guardrails
- Facility search/profile: which healthcare programs are reported at a location? Show source context, not unsupported physical-property assertions.
- Service market: how many provider records report a defined specialty or service? Show reporting coverage, missing values, scope and as-of date; never convert to installed equipment or service demand.
- Capacity research: aggregate reported certified beds, dialysis stations, operating rooms and procedure rooms **separately** by dataset and unit.
- Compliance research: display historical citation and survey timeline, domain, status and dates separately; no open-violation count without a qualified resolution model.
- Portfolio research: display source roles, reported organization names, effective dates and match evidence; distinguish operator, manager, ownership and legal property owner.
- Data quality/source explorer: show dataset period, release hash, definitions, profile coverage and unresolved/blocked states; no raw or restricted data.
- Sales research: evidence-supported research contexts (e.g., dialysis, life safety, infection prevention, imaging, surgical infrastructure), not confirmed buying intent, risk scores or invented contractor connections.

## Stop conditions / definition of done
Every one of the 19 release schemas is fully inventoried; each original field is defined with evidence or explicitly blocked/excluded; all accessible raw columns are value-profiled against their pinned hashes; actual projections and join coverage are reconciled; useful fields have reviewed application mappings and permitted-use status. Remaining blocked rows/fields have precise evidence and a specific next action. Completed source batches require independently reproducible aggregates, no unsupported conclusions and no regression. Track completion per stage rather than marking the entire data project complete based on header inventory.

## Current constraints and decisions
This work examined repository code, historical qualification evidence, exact registry headers and four actual public shards. Five large public files were truncated by the connector; raw originals and full national SQLite snapshot were unavailable for direct processing. No new national reconstruction, raw release retrieval, storage provision, production schema, ingestion change, UI redesign, data redistribution, deployment, or promotion was performed. The documentation branch is isolated to avoid conflicting with the existing custodian. The user requested focus on data understanding; the precise phase ordering, status taxonomy and proposed entity model are engineering decisions for review, not approved production changes.
