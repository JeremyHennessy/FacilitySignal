# FacilitySignal — full pinned national field profile and semantic audit

**Date:** 2026-11-26. Direct user-requested data-understanding work; no custodian handoff. Evidence branch `docs/data-understanding-20261126`; base of original audit `5ed5eeceae8c258c1d7c1d780162c274603060cd`. No main promotion, production data publication, ingestion behavior, data schema, or UI changes.

## Qualified scope

The [national evidence index](../research/national_data_understanding_index_20261126.json) reconciles every original column and every retained source record across the 19 pinned integrated releases. It references exact source hashes, profile artifact paths, prior mappings, and definition-review state.

| Family | Sources | Retained records checked | Original columns |
|---|---:|---:|---:|
| Care Compare provider files | 7 | 48,004 | 419 |
| Care Compare citation files | 2 | 619,069 | 48 |
| QIES | 1 | 13,598 | 473 |
| iQIES | 1 | 100,334 | 186 |
| CLIA | 1 | 686,058 | 103 |
| QCOR hospital surveys | 1 | 284,391 | 18 |
| PECOS | 6 | 152,606 | 186 |
| **Total** | **19** | **1,904,060** | **1,433** |

The original source counts reconcile to 2,230,841 input rows, including 326,781 intentionally excluded individual-owner rows. These individual rows were skipped before column profiling. 125,518,335 retained cells were assessed: 1,402 columns have aggregate value/lexical profiles and 31 restricted columns have presence-only profiles. 299 fields are completely blank in their pinned source releases (288 QIES, 3 CLIA, 8 PECOS organizational owner files including restricted personal-name fields). Distinct nonmissing value counts are exact for 1,201 fields, and bounded lower counts for 201 fields. Never treat capped cardinality as exact or blank as zero. No raw values, provider narratives, personal owner rows, or full raw database retained in this repository. No claim of permanent private raw storage. Source records are not unique healthcare properties or active operations.

## Reproducible execution evidence

- [Run 45821921407](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45821921407), exact candidate `bc4bba6360a650eea2624b377cc7c1c246f01511`, succeeded: 762 actual raw POS columns, all 799,990 rows; exact original 653 Care Compare/PECOS headers recovered from two small historical audit manifests. All source hashes/row totals/column orders checked. No full database reconstruction.
- [Run 45822384234](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45822384234), exact candidate `1a946bc562100c6497cf9426021e66000fd693d5`, succeeded in all four matrix jobs: 16 remaining sources, all 671 columns, 1,104,070 retained records. Original PECOS individual-owner exclusion count reconciled. QCOR four narrative fields assessed for presence only; no narrative text analyzed or published. All actual original checksums and headers matched pinned releases.
- [Run 45822686294](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45822686294), exact candidate `dbd988b92c754ff447e777052c88fb89fd418532`, succeeded for both historical layouts. Earlier run 45822532848 failed before PDF extraction because pdftotext was missing; replaced the unavailable diagnostic dependency with pinned Python layout extraction. The original 2023 QIES PDF hash was reconfirmed, and the CLIA PDF hash recorded. Exact names and candidate descriptions were found for 473 QIES and 103 CLIA fields. Historical definitions are not automatically Q3 2026 semantic approval. QIES has 18 fields with multiple candidate definitions, which must remain provider-category-scoped. Some parsed labels/types are incomplete; page references and full diagnostic artifacts remain available for review.
- Existing iQIES current-release publisher metadata: 184 unique definitions of 186 original fields; [manual semantic/application crosswalk](../research/iqies_semantic_application_crosswalk_20261126.json) covers all 186, flags 24 fields, and blocks 5 field definitions/applicability mappings. Only the original bounded capability/status projections remain approved within their existing scope.

## Important evidence-backed findings and application candidates

| Evidence | Confirmed observation | Proposed use and gate |
|---|---|---|
| Long-term hospital `Total Number of Beds` | 305 whole-number records totaling 21,765; six nonnumeric/other tokens; old adapter alias omitted this header | Source-specific reported total-bed measure (not certified beds), after validating the six tokens and unit-aware mapping; no blind zero or mixed-unit total. |
| Home health `Type of Ownership` | 12,409 populated rows, four exact distinct tokens; old alias list did not include this exact header | Ownership classification; qualify code/domain and add the smallest source-specific mapping. |
| Hospital `Emergency Services` | 4,501 literal Yes; 934 No | Reported service filter with source period, not real-time availability. |
| Nursing `Chain ID` and `Number of Facilities in Chain` | 10,227 populated records, 612 distinct chain IDs; 4,459 blank | Evidence-linked source chain groups, not independently resolved ultimate owner; avoid summing repeated chain totals. |
| SNF PECOS `AFFILIATION ENTITY ID` | 10,162 populated, 613 distinct; 4,239 blank | Affiliation evidence, separate from chain ID or legal property ownership until validated join. |
| QIES `CLIA_ID_NUMBER_1` | 6,081 populated, 7,517 blank | Potential direct hospital-to-lab identifier join; first qualify exact scope, matching and duplicates. |
| CLIA `AFFILIATED_PROVIDER_NUMBER_1` | 111,204 populated; no resolved affiliation claim | Candidate reverse relationship only; not unique labs or ownership. |
| CLIA `CRTFCT_TYPE_CD` | All 686,058 rows populated, five distinct tokens | Historical certificate domain includes compliance, waiver, accreditation, provider-performed microscopy and registration. Verify actual current code counts and scope before use. |
| CLIA test volumes | Multiple source fields populated, but application-form, accredited, survey-verified and estimated waived counts differ in definition and applicability | Separate laboratory market-size measures and units, no summation of potentially overlapping counts or installed analyzer inference. |
| Nursing citations `Citation under IDR` and `Citation under IIDR` | Both source files have populated fields with two distinct tokens each | Add dispute-state evidence after current code definition qualification; do not infer open findings or resolved status. Fire source also has populated `Tag Version`; health source does not have this header. |
| QCOR | All 18 raw columns inventoried; 14 structured fields profiled, four narrative fields presence only | Historical survey event/tag/memo evidence, never narrative redistribution or current deficiency inference. |

### iQIES actual service provision comparison

Q3 2026 ASC scope 8,492 source records. For pharmacy, laboratory and radiology each has 8,040 records with exact documented provision codes and 452 unavailable. The current iQIES publisher mappings distinguish direct provision, outside-source provision, combination and not provided. Counts are source-reported provision mode, not installed equipment, vendor contracts, confirmed procurement or live operations.

| Service | Direct | Outside source | Combination | Not provided |
|---|---:|---:|---:|---:|
| Pharmacy | 1,068 | 4,947 | 371 | 1,654 |
| Laboratory | 1,161 | 4,961 | 513 | 1,405 |
| Radiology | 2,250 | 3,484 | 290 | 2,016 |

HHA laboratory provision uses a different M5 string domain; do not apply ASC numeric codes to HHA. Pharmacy has substantial nonblank values outside its publisher ASC scope; do not promote those observations automatically. One ASC operating-room count is 5,112, an extreme source value requiring independent review. Four operating-room tokens did not meet the current numeric profile. Preserve original evidence rather than silently replacing or dropping the outlier. No approved aggregate market sizing from unadjudicated counts. The historical QIES `OPRTG_ROOM_CNT` description also says ASC despite appearing in a hospital-category section; do not assume hospital room semantics from its name.

## Next technical gate (not a declaration of completion)

Every original column is now inventoried and assessed. All 762 registry fields have a current or historical publisher-metadata crosswalk or explicitly unresolved state; the 671 other original fields have exact headers and actual profiles, but still require systematic current publisher-definition/domain review. Existing code aliases and lexical shapes are not substitutes for definitions. Carry forward the data index as the field-by-field work ledger: verify current QIES/CLIA definitions against historical candidates; resolve iQIES inconsistencies and applicability conflicts; review current Care Compare and PECOS dictionaries, clinical measure/footnote domains and source-specific flags, then qualify minimal data-layer enhancements against pinned data. Preserve scope, date, unit, source lineage and missingness; do not use clinical metrics as property risk scores. Do not change approved UI or expose additional row-level sources without review. No source acquisition beyond the targeted pinned source files and two publisher dictionaries was needed for this pass.
