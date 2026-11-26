# QIES hospital infrastructure and service field audit — November 26, 2026

## Qualified inputs and scope

[Qualification 45829855217](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45829855217), executed commit `82ac2093f214104fdeac4d16d272476209785ffd`, passed all targeted tests and reconciled 13,598 raw records, exact 473-column header, 10,757,357 bytes and the pinned Q3 2026 SHA-256. [Aggregate evidence](../research/qies_hospital_infrastructure_audit_20261126.json) preserves the field names, descriptions, historical code domains and physical/printed page references. Reused the exact historical layout crosswalk artifact 15118642285 from run 45822686294 (SHA-256 77babffa7f65e903664813f845ff68a182610d2ee9073fda8151241a28a3503d). No fresh PDF or national database retrieval. Scope limited to first hospital category 01 section, physical pages 1–59, to prevent leakage of nursing-facility definitions across the historical parser's category boundary. The publisher's 2023 layout remains historical evidence, not independently verified 2026 semantics.

120 fields: 57 service-provision codes (45 additional to prior 12), 31 capacity and affiliation/offsite count fields, 20 FTE workforce counts, eight literal flags, four status/classification codes. One additional count field, OPRTG_ROOM_CNT, remains explicitly blocked because the hospital section describes an ASC. Reconcile all 12 existing service distributions exactly. All 57 service fields use literal 0/1/2/3 or blank in this release; no unmatched nonblank service token. The historical meanings are 0 not provided, 1 provided by staff, 2 under arrangement, 3 both. Missing is not code 0. Eight flags are Y/N or blank; their full code domains are not asserted from the old layout.

## Source-scoped comparison, not physical-site identity

The already-published November 12 hospital Care Compare projection (5,435 records) is checksum-reconciled against the market-summary metadata. Of the 13,598 historical QIES category 01 rows, 5,425 match exact reported six-character CCN and state; no duplicate QIES candidates within those matching public keys. 5,021 pairs also corroborate literal normalized street/city and ZIP5 text. Ten Care Compare records have no exact candidate. No canonical site resolution. Of the QIES rows, 7,033 report program code 00, historically labeled active provider; 5,362 of these have a same-state Care Compare candidate, 1,671 do not. Other historical program codes occur on 6,565 rows, including 63 with a Care Compare candidate. Thus even matched public directory records are not proof of current operation.

Separate disjoint diagnostic populations: 5,362 code-00/same-state candidates; 1,671 code-00 without same-state candidate; 6,565 other program codes. 154 rows in the 5,362 subset are skeleton records (limited survey data). No current compliance or operational-status conclusion from these fields.

## Selected observations (5,362-row candidate subset)

| Service | Staff | Arrangement | Both | Not provided | Blank |
|---|---:|---:|---:|---:|---:|
| Pharmacy | 3754 | 562 | 769 | 123 | 154 |
| Clinical laboratory | 3000 | 668 | 1364 | 196 | 134 |
| Acute renal dialysis | 823 | 1207 | 295 | 2903 | 134 |
| Anesthesia | 1245 | 2229 | 691 | 1063 | 134 |
| CT | 3332 | 177 | 431 | 1288 | 134 |
| MRI | 2269 | 862 | 509 | 1588 | 134 |
| Dental | 673 | 729 | 179 | 3647 | 134 |
| Dietary | 3073 | 1085 | 813 | 257 | 134 |

These are historical source code observations; provision by arrangement is not a confirmed vendor contract, current availability, installed equipment or purchase intent. Blank coverage differs (134 or 154). The published subset should be titled by actual selection criteria rather than "active hospitals."

Reported positive counts (source records, not physical sites or quantities summed): 2,638 offsite location counts; 1,024 offsite emergency department counts; 1,608 affiliated-provider totals; 171 affiliated ESRD counts; 623 affiliated home-health counts; 434 affiliated SNF counts; 2,474 endoscopy procedure-room counts; 1,299 cardiac catheterization procedure-room counts; 1,589 psychiatric unit bed counts; 1,162 rehabilitation unit bed counts.

## Cross-field diagnostic results

All 5,362 comparable subset certified beds are at or below reported total beds. The offsite component arithmetic agrees with the reported total for all 5,362; the affiliated component arithmetic agrees for 5,354 and is below the total for eight. This arithmetic is diagnostic, not independent proof of additivity or ownership. Psychiatric and rehabilitation unit flags align with the positive-versus-zero bed counts in this subset.

Cardiac catheterization: 56 subset rows report positive rooms but service code 0; 419 staff-only and 57 combined-staff/arrangement rows report zero rooms. Arrangements can be offsite and historical fields may differ in dates; do not automatically reject or normalize these observations. One reported room-count maximum is 598. Operating-room count is blocked even though the raw column has 3,473 positive rows, 10,108 explicit zeros, 17 blanks. The source dictionary contradiction must be resolved before treating it as hospital OR inventory. FTE ranges are diagnostic only, including reported maxima of 64,782 RN FTE and 52,900.15 PT FTE in the subset. No summed staffing or market-size claims are approved. Do not silently drop or correct outliers.

## Application plan and limits

Use narrowly selected aggregate distributions for service provision, reported positive-count evidence and source identity coverage. No new individual hospital service or infrastructure rows, names, identifiers or relationship links are authorized for publication. Numeric sums remain diagnostic pending outlier review and source semantics. Keep the existing 12 field observations and historical code labels unchanged, and separate the 5,362-row subset from national counts. Future local source-scoped hospital evidence can be enabled after release-lineage and record-level corroboration checks, with explicit unresolved historical status and reuse review. Preserve exact source values and document any future mapping changes.
