# FS-040 — CMS hospital HAI aggregate qualification gate, 2026-11-28

Official catalog observations (not CSV ingestion):

- [Hospital](https://data.cms.gov/provider-data/dataset/77hc-ibv8): 172,332 records and 15 columns.
- [National](https://data.cms.gov/provider-data/dataset/yd3s-jyhd): six rows and six columns. The complete displayed table has HAI_1_SIR through HAI_6_SIR, all six scores equal to 1, no displayed footnotes, reporting window 2025-01-01 through 2025-12-31.
- [State](https://data.cms.gov/provider-data/dataset/k2ze-bqvw): 1,008 records and seven columns, separate state grain, not yet acquired.
- All three catalog editions: modified 2026-10-19; released 2026-11-12.

The six national reference values are not a measured pooled infection rate and do not prove that national infection incidence was unchanged. [CDC SIR guidance](https://www.cdc.gov/nhsn/ps-analysis-resources/keys-to-success.html) explains the ratio of observed to predicted infections and the role of uncertainty. The actual CMS baseline model version is not yet qualified; no cross-baseline comparison. No HAI measure establishes water contamination, building equipment failure, contractor fault or a procurement need.

The new collector independently verifies the release, API count, strict headers and bounded original bytes, retains aggregate-only evidence and stops on changed metadata, schema or access failure. Individual provider names, addresses, scores and identifier values are not emitted. No raw artifact, private archive writes or app publication. Source-specific reuse review remains pending. The national grain and provider grain are distinct; fixture validation is not publisher acquisition.

## Actual execution outcome

- [First candidate run 46131203759](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/46131203759): four of five tests passed; the undercount test correctly raised `provider reconciliation` but its assertion expected different wording. Both publisher steps skipped.
- Corrected assertion only, candidate `c25e21dc7f45c4c971f573b69fcfa1bb19fcf39b`. [Run 46131236300](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/46131236300), job 140936612618: five of five fixture tests passed; the national publisher metadata request `/provider-data/api/1/metastore/schemas/dataset/items/yd3s-jyhd` returned HTTP 403 before count or CSV retrieval. Provider step skipped. No new rows, source hashes or database files acquired. Stop acquisition retries; no alternate access path attempted. Do not treat the complete displayed six-row national catalog table as checksum-verified CSV evidence. No promotion.
