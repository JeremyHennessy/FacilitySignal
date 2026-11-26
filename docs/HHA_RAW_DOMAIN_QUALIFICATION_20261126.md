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

## Actual qualification result

[Run 45910250093](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45910250093), job 140216613363, exact candidate 460c6a1d82f62d4de821b9e0d9b396a2b90ee933. Six tests passed; one pinned publisher retrieval and audit succeeded. Aggregate-only artifact 15159498474, digest sha256:762b8344e9bca8a057606cfe39b95582b15ca12e16467afb7d0abd876e07ac48, expires 2026-12-26T23:19:38Z. [Durable log summary](../research/hha_raw_domain_log_summary_20261126.json).

- All 12,409 records and 96 headers reconciled with the source SHA. Ratings: 8,126 valid half-star values and 4,283 dashes. Certification date: 12,408 calendar dates at or before release, one dash.
- Ownership: 2,167 dashes and 10,242 rows with three distinct labels outside the exact case-sensitive dictionary allowlist. Do not call the labels invalid or presume the cause; exact labels and applicability still require review. No new ownership mapping or filter approved.
- Across sixteen relationships, 107716 jointly numeric numerator/denominator observations, 6908 numerator-only, 6972 denominator-only, 76948 neither. No jointly numeric numerator exceeds its denominator. These are measure-row observations, not unique agencies; do not reconstruct missing counts or compute clinical rates from incomplete rows.
- Across the three claims interval groups, 21597 complete numeric interval triples were ordered and 15630 were incomplete. This is an order check, not validation of confidence coverage or rate scale.
- No new UI/clinical scoring approval, Blob writes, or national rebuild. Full per-field artifact retained; durable summary contains exact emitted log values, not an independent extraction of every field. Next: resolve source ownership labels against dictionary without another full download if feasible; examine detailed receipt, scale and footnote semantics; then review next unqualified Care Compare source.
