# iQIES full publisher dictionary checkpoint — 2026-11-26

## Verified execution

Targeted [qualification run 45820947232](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45820947232), diagnostic commit `2de09114e8cd78f8856826e9c8904d0300309eb8`, job 139912727780, succeeded; 28 diagnostic-branch tests passed. Downloaded only the previously identified 40,305-byte CMS October 2026 dictionary workbook, verified exact pinned SHA-256 `bd68d76dc72ee5c3b3249c459644ff2ed90c8e8cf6e182b76742ec53164c0594`. No provider data redownload. The prior diagnostic commit `0319a6fb97303bd7d33a88dc05c991aa91d1e91e` remains preserved in history.

The [full publisher metadata crosswalk](../research/iqies_full_dictionary_metadata_20261126.json) retains source order, all candidate worksheet rows, exact field header, format, label, definition, applicability, mapping references and all mapping-sheet rows. The 186 entries reconcile against the exact pinned iQIES source headers, and 25 previously reviewed field references reconcile by worksheet row. The existing 13 bounded capability/status projections remain unchanged. This is extraction and reconciliation of publisher metadata, not completion of full semantic, actual raw-domain, or publication review.

| Measure | Result |
|---|---:|
| Original pinned iQIES columns | 186 |
| Unique publisher definitions with applicability | 184 |
| Missing dictionary field | 1 |
| Ambiguous dictionary field | 1 |
| Publisher mapping sheets | 12 |
| Publisher mapping rows | 147 |
| Unique fields with exact mapping-sheet reference | 26 |
| Unique fields with annotated unresolved mapping reference | 1 |
| Unique fields without explicit mapping-sheet reference | 157 |

Missing: `fed_fundd_fqhc_sw`. Do not invent a definition from the abbreviated name. Ambiguous: `physn_arngmt_sw`, worksheet rows 158 and 159, both CORF-related, with different definition text. Preserve both; no automatic resolution. The annotated `gnrl_fac_type_cd` reference is to M8 with an HHA-only qualification; no generic mapping should be inferred. Scope-qualified mappings and literal missing tokens must remain distinct. A blank Mapping cell does not establish the absence of a source domain.

## Application implications (documented publisher semantics, not yet observed-value qualification)

- M5 differentiates ASC direct provision, outside-source provision, combination, and not provided with codes 1/2/3/4. HHA uses a different set of string codes in the same table, including COMBO, HS, NP, PAS and UA. Never apply ASC numeric codes to HHA or use one generic service mapping.
- M7 distinguishes ASC radiology provision using the 1/2/3/4 domain. Pharmacy and laboratory provision use M5 within their specified provider scopes. These are service provision modes, not equipment ownership or contracts with named vendors.
- The dictionary contains nursing-home specialty bed counts (e.g. ventilator, dialysis, rehabilitation), separate from all-bed counts and from certified capacity. Respect scope, units, subset relationships and potential overlap. No totals without inspecting actual raw values.
- Home health and hospice provision fields, ESRD service indicators, ASC specialty fields, CORF staffing arrangements and certification evidence can support type-specific profiles after normalization and scope review.
- The definition of `prvdr_num` specifies six or ten positions; preserve source identity as text and distinguish CCNs from physical property IDs.
- The exact mapping rows are publisher dictionary metadata, not actual source observations. Raw source value distributions, active status, service availability, equipment, commercial reuse and application qualification remain separate gates.

## Durable next gate

Complete the human-readable interpretation and application mapping of the 184 unique metadata fields, with explicit disposition of two unresolved fields. Reconcile each mapped domain against actual raw values in the pinned iQIES registry where authorized storage/recovery permits. Obtain exact QIES and CLIA dictionary crosswalks next; recover all original Care Compare and PECOS headers from qualified manifests before additional broad acquisition. Do not repeatedly reconstruct the national database or fetch the same dictionary merely to reproduce this extraction. Continue actual aggregate profiling and tested source-scoped views. No production schema, ingestion, UI, Pages or public provider-level data changes in this workstream.

The full extractor and synthetic regression test are included in the documentation branch for reuse with a verified local workbook; the targeted diagnostic branch used the existing iQIES qualification workflow. No new scheduled tasks or paid infrastructure.
