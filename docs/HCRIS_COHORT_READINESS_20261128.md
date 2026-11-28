# FY2024 HCRIS cohort readiness — 2026-11-28

Reconciled existing public aggregate evidence at main 13f9a9ecbd5300af263b38e0d4e2c9f5ebcfeebf. No Azure reads, publisher downloads, row-level joins or retention performed. The direct crosswalk, three-way report audit, capacity rehearsal and archive inventory have matching source checksum pins, report-key intersection sizes, candidate cohort counts, and index/numeric shard totals for both forms. Input blobs respectively: 7dba1fe969c1e0b7d9e82345175dd8e65c4bc3a7, bddd4c5fa098d940f48757443ce7fc8417e0adc6, 0b1f7306ac06873c36c9d43c3f899796bc8a94ad, 420b6591d6b75dc10f8c4f564f5143c346611e0b.

For the common pinned report-key universe N, cohort size C and exact-decimal parity count E, the number of candidate reports with equal values is bounded by max(0,C+E-N) and min(C,E). This assumes the previously documented cohort is a subset of that exact intersection. These are bounds, not measured joint membership, facility counts, dollar amounts or live observations.

| Form | Report intersection | Three-way candidate reports | Previously screened numeric rows |
|---|---:|---:|---:|
| Hospital | 4,339 | 3,561 | 19,440,697 |
| SNF | 13,772 | 13,408 | 13,769,215 |

| Measure | Minimum candidate parity | Maximum |
|---|---:|---:|
| Hospital total costs | 3,482 | 3,561 |
| Hospital net patient revenue | 3,350 | 3,561 |
| SNF total costs | 13,182 | 13,408 |
| SNF contract labor | 9,751 | 10,115 |

The other measures are produced by the reproducible aggregate-only audit (17 measure/form combinations total). Contract labor has 3,657 absent values in the full SNF report intersection, so it is not an all-provider measure. Monetary scale, joint row-level qualification, reuse and financial attribution remain unresolved. No aggregate bound grants approval to expose a provider's financial data. Next gate is an exact private joint report-key audit using the authorized pinned inputs, only after confirming the cost/rights boundary. Historical capacity fields are distinct from current operational capacity.

Run: python -m scripts.audit_hcris_cohort_readiness; python -m unittest discover -s tests -p test_hcris_cohort_readiness.py.
