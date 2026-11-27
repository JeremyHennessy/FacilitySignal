# QIES projection gap — historical dictionary and lexical reconciliation (2026-11-27 UTC)

Reviewed all 162 populated aggregate fields outside the original projection, using three pinned evidence blobs and the original 13,598-row Q3 2026 source digest. The CMS API catalog independently confirms Q3 2026 version b1e5b072-5e82-4e37-9bd6-de8708679935, 473 columns and 13,598 rows; last updated October 16, 2026. [Publisher API metadata](https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/provider-of-services-file-quality-improvement-and-evaluation-system/api-docs).

| Disposition | Fields |
|---|---:|
| numeric_lexical_candidate | 53 |
| integer_text_max_width_eight | 10 |
| text_or_code_unverified | 91 |
| historical_type_missing | 5 |
| historical_definition_conflict | 3 |
| Total | 162 |

The historical March 2023 fixed-width layout is not a current-release codebook. Numeric lexical candidates are not validated counts, units, precision, ranges or additivity. Ten historical date fields contain integer-shaped text with maximum width eight; this does not establish eight digits in every cell, date order, calendar validity or recency. The 91 text/code fields have no reconciled code distributions. Three fields have conflicting historical descriptions (SSA_STATE_CD, CRTFCTN_ACTN_TYPE_CD, CBSA_CD); five lack a historical type candidate. Current profile contains no provider scope breakdown or documented code counts. None of the 162 is newly domain-qualified or approved for application publication.

Potential follow-up: ownership-change count (CHOW_CNT), affiliated ambulance and ASC counts (TOT_AFLTD_AMBLNC_SRVC_CNT and TOT_AFLTD_ASC_CNT) and other institutional service/capacity measures, only after release-specific definitions and actual domains/units are verified. Affiliation counts do not establish named relationships, properties, active operations or equipment. An acceptable plan of correction flag cannot establish current compliance. Retain all ambiguity and missingness.

No new publisher payload download, row-level publication, production UI change, or canonical matches. [Aggregate receipt](../research/qies_projection_gap_lexical_review_20261127.json). Regression tests independently reconstruct all dispositions and verify pinned evidence, exact ordinals, source counts and negative controls.
