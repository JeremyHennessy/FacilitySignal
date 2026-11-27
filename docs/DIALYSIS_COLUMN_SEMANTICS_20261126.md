# Dialysis directory column semantic review

Release: 2026-10-28; 7,471 records, 146 exact source columns. Source SHA-256: `9b0232d73b8aa9628b51bc76b7246b8590daa0393ec9dfd3126171ce571469ed`.

Machine-readable overlay: [dialysis_column_semantics_20261126.json](../research/dialysis_column_semantics_20261126.json). Every field has its exact source ordinal/header, a semantic interpretation, unit, extracted dictionary table/page reference, pinned aggregate profile and application disposition. The existing clinical diagnostics are retained from [qualification 45841298990](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45841298990). No source rows were downloaded again.

## Qualification boundaries

The [publisher dictionary](https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/dialysis/DF_Data_Dictionary.pdf) has inconsistent text and rendered versions. Extracted directory tables carry an October 2026 title and July 2026 footer, while rendered pages 2–3 carry January 2026 and printed page 35 carries April 2025. This is semantic routing, not confirmation of exact current-version equivalence. References are to extracted printed pages. Code semantics remain provisional; preserve literal leading zeros. No new domain or publication approval is granted.

| Routing | Fields |
|---|---:|
| Institutional/identity context (existing or candidate) | 18 |
| Clinical context only | 127 |
| Restricted contact presence only | 1 |
| Total | 146 |

All 24 availability-code distributions reconcile to 7,471 records per field. In the Five Star cross-check, 2,695 numeric ratings and 86 blanks carry code 281; numeric does not mean current-year qualified. The 2,781 records with code 280 in several clinical measures must not be assigned a zero or poor-performance value. The infection ratio has 6,402 numeric estimates but only 4,269 complete intervals; hospitalization has 7,267 numeric estimates but 7,266 complete intervals. Missing confidence limits must not be reconstructed. These are reporting/quality diagnostics, not adverse property findings.

Care Compare station count and iQIES approved stations have different definitions and must never be added. Clinical data are isolated from property scoring. Existing service projection and approved UI are unchanged. Next steps: obtain exact version evidence, validate dictionary domain semantics and actual numeric ranges, and review candidate institutional fields before proposing any new application mapping.
