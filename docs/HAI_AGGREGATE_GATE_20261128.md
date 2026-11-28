# FS-040 — CMS hospital HAI aggregate qualification gate, 2026-11-28

Official catalog observations (not CSV ingestion):

- [Hospital](https://data.cms.gov/provider-data/dataset/77hc-ibv8): 172,332 records and 15 columns.
- [National](https://data.cms.gov/provider-data/dataset/yd3s-jyhd): six rows and six columns. The complete displayed table has HAI_1_SIR through HAI_6_SIR, all six scores equal to 1, no displayed footnotes, reporting window 2025-01-01 through 2025-12-31.
- [State](https://data.cms.gov/provider-data/dataset/k2ze-bqvw): 1,008 records and seven columns, separate state grain, not yet acquired.
- All three catalog editions: modified 2026-10-19; released 2026-11-12.

The six national reference values are not a measured pooled infection rate and do not prove that national infection incidence was unchanged. [CDC SIR guidance](https://www.cdc.gov/nhsn/ps-analysis-resources/keys-to-success.html) explains the ratio of observed to predicted infections and the role of uncertainty. The actual CMS baseline model version is not yet qualified; no cross-baseline comparison. No HAI measure establishes water contamination, building equipment failure, contractor fault or a procurement need.

The new collector independently verifies the release, API count, strict headers and bounded original bytes, retains aggregate-only evidence and stops on changed metadata, schema or access failure. Individual provider names, addresses, scores and identifier values are not emitted. No raw artifact, private archive writes or app publication. Source-specific reuse review remains pending. The national grain and provider grain are distinct; fixture validation is not publisher acquisition.
