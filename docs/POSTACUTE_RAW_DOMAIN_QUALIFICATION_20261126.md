# Postacute raw domain and ownership reconciliation — 2026-11-26

Verified base 14bd1ced9ee6ce426b50f7180a48ef889bbbc866, main CI 45911045045 and Pages 45911044564 succeeded. The original archive retains normalized snapshots, not original publisher CSVs. This bounded candidate retrieves only the exact pinned hospice, LTCH and rehabilitation releases (1,039,106 bytes total), validates bytes/SHA-256/header/rows, compares six public identity fields with the existing shard, and audits documented ownership categories, calendar dates, CMS regions, secondary-address markers, CCN/ZIP shape and telephone presence. LTCH reported total beds must reconcile both the retained aggregate and every existing public capacity value. No storage or application change, no new row-level publication. Source identity comparison is not canonical matching.

CMS regional reference: [regional offices](https://www.cms.gov/about-cms/where-we-are/regional-offices) and [CMS MCD help](https://www.cms.gov/medicare-coverage-database/help/all-page-help-text.aspx), which explicitly enumerates regions 1–10 including AS, GU and the Northern Mariana Islands. The latter is a separate administrative reference; mismatch is review evidence, not proof of error. Ownership mappings admit only exact trimmed dictionary labels and casefold equality; hyphen/whitespace variants are candidates only. Unknown raw strings never emitted. Date checks establish syntactic/calendar and release cutoff validity, not current operating status.

## HHA reconciliation (no retrieval)

Same source SHA in research/qualified_data_use_20261126.json, research/hha_raw_domain_log_summary_20261126.json and source lock: 7adf3e17961949bbd64ef243545aa387224d9837e8c5601476f5b11946e76d22. Prior qualified_data_use.py classifies the exact field using explicit dictionary labels with trim+casefold. Aggregate result: Proprietary 8,954; Non-Profit 1,049; Government Operated 239; dash 2,167. All 10,242 non-dash records are accounted for, exactly matching the case-sensitive raw audit's unmapped total. Prior audit's three distinct non-dash labels agree in cardinality with the three mapped categories. Exact original raw spellings were not retained, so do not assert individual capitalization. This supersedes the unresolved aggregate HHA classification issue, not its raw spelling or legal ownership qualification. No new HHA download or filter approval.

No new clinical, commercial risk or legal ownership inference.

## Actual qualification — passed

[Run 45911231291](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45911231291), job 140219849194, candidate baa522b334cabe6eabd4d34e2aaa7929941baac9. Five targeted tests passed. Three exact CSVs retrieved, totaling 1,039,106 bytes. All 8,003 records, 37 headers and source SHA-256 pins reconciled. Six institutional identity fields matched existing public directory records for every record, not canonical site resolution. All state/region comparisons matched the independent CMS reference; no CCN or postal shape exceptions. [Full aggregate log receipt](../research/postacute_raw_domain_receipt_20261126.json); artifact 15159509769, sha256:4bd7a51faa86b1e9bab8d3a796fd6da7d03077420727cc3aef06e78b6047270f, expires 2026-12-26T23:29:35Z.

| Category | Hospice | LTCH | IRF |
|---|---:|---:|---:|
| For profit | 4479 | 217 | 545 |
| Non-profit | 804 | 81 | 569 |
| Government | 101 | 11 | 100 |
| Physician | not in dictionary | 1 | 8 |
| Tribal | not in dictionary | 1 | not in dictionary |
| Other | 428 | not in dictionary | not in dictionary |
| Combination government/non-profit | 0 | not in dictionary | not in dictionary |
| Dash missing | 658 | 0 | 0 |

All nonmissing ownership values reconcile under exact-trimmed or casefold equality; no punctuation candidates or unknown labels. No arbitrary source strings published. Category-specific taxonomies retained; do not infer legal or property title.

Dates: hospice 6,470 and LTCH 311 valid calendar dates at/before release, IRF 1,220 at/before release and 2 valid calendar dates after release. The latter are unresolved temporal exceptions; do not silently correct or call them fraudulent. Secondary address dashes: hospice 5,891, LTCH all 311, IRF 1,154; no contact values retained. LTCH 305 integer values, sum 21,765, min 9, max 760, no zero, six dash markers. All 311 capacity values match existing public projection. No new public field or risk-model approval. Exact HHA raw spelling, IRF date provenance, and source-specific reuse/projection authorization remain separate gates.
