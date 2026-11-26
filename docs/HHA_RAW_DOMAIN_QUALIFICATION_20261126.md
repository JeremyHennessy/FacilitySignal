# HHA raw domain and reporting-period qualification candidate — 2026-11-26

Base: 11628dddb45c6c309a02d28d54ce68763d27d29e; main verification 45904974497 and Pages 45904973802 succeeded. Prior semantic overlay covers 96 exact columns of the October 21 release. The national archive explicitly omits raw originals (see AZURE_NATIONAL_ARCHIVE.md); no national rebuild is warranted. This candidate permits exactly one bounded 12,508,977-byte publisher retrieval on the dedicated branch, checks the pinned SHA-256, and emits aggregate counts only. It does not write Blob, raw data, UI or production pointers. Unknown ownership strings are counted but not emitted.

## Publisher review

[CMS measure dates catalog](https://data.cms.gov/provider-data/dataset/c886-nwpj), 18 rows and two columns, release October 21 2026, inspected published table. [October CMS refresh notice](https://www.cms.gov/medicare/quality/home-health-quality-reporting-program/home-health-hh-quality-reporting-program-qrp-public-reporting) independently confirms periods. Catalog metadata has not been byte-pinned. Concept-level mapping to existing field overlay, not exact label equality:

| HHA overlay ordinals | Period |
|---|---|
| 18–69, 13 assessment measure groups | 2025-01-01 through 2025-12-31 |
| 70–77, DTC | 2024-01-01 through 2025-12-31 |
| 78–85, PPR | 2023-01-01 through 2025-12-31 |
| 86–93, PPH | 2025-01-01 through 2025-12-31 |
| 94–96, Medicare spending score and episode count | 2023-01-01 through 2024-12-31 |

Do not give the rating field an inferred measure-date row or conflate quality periods with release date. The 18 rows correspond to 13 assessment groups, three claims outcome groups, and two spending entries. No HHCAHPS rows included in the provider file.

[CMS dictionary v14.0](https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/home_health/HHS_Data_Dictionary.pdf), printed pages 10 and 47 visually reviewed: ownership categories are Non-Profit, Proprietary, Government Operated; star ratings use half-star increments from 1 to 5. Footnotes 1–13 have documented meanings; 14–16 are HHVBP-only. Keep unknown/unmapped values distinct. Footnote syntax alone does not establish applicability or missing-data reason. A prior dictionary with more granular ownership categories must not override the current dictionary.

The audit tests integer count bounds, percentage candidate bounds, rating step, date syntax/calendar/range, counts coavailability, numerator/denominator inequalities and interval order. Rate/spending scale remains unresolved; observed numeric ranges are descriptive diagnostics, not validated scale. Numeric outliers are review findings, not automatic source errors. No reconstruction of suppressed values. All clinical metrics remain excluded from property/service-risk scoring. No new application approval.

## Gate

Candidate only. Inspect actual CI receipt and reconcile against previous lexical counts; adjudicate unexpected ownership, missing markers, date anomalies, footnotes and arithmetic before production promotion. Keep full raw values private and avoid further downloads unless a specific confirmed gap requires them.
