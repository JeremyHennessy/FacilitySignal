# Nursing provider directory — all 102 fields reviewed

Pinned October 28 2026 source: 14,686 provider records, 102 exact columns, SHA-256 `ab70309ae6f0ee86b19fe9acb61a6d2953f970d3b09e80bb9b090e4b19ce35a2`. [Machine-readable review](../research/nursing_column_semantics_20261127.json) binds each header and ordinal to a paraphrased definition, unit, reporting/usage disposition, exact retained aggregate profile and previous domain evidence where applicable. No publisher CSV redownload, no new application field approvals.

## Dictionary revision adjudication

[CMS dictionary](https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/nursing_home/NH_Data_Dictionary.pdf), Table 2 printed pages 8–12, Table 15 p25 and Table 16 p26: visually inspected. Table 2 and revision table rendered with June 2026 footers, footnote table with May 2026. October 2026 extracted text contains 102 provider columns; the older rendered Table 2 contains 99. Ordinals 29, 75, 84 are documented as September 2026 additions in extracted Table 16 (high-performing designation and two standard-survey footnotes). The extracted revision adds code 29 for risk-based survey; the older rendered footnote table lacks it. Do not equate the render with the October text. Three text-only definitions are provisional, and exact dictionary bytes/release equivalence remain unverified. The public catalog response visible during this review likewise reflected the earlier June release; do not treat it as evidence of the pinned October bytes.

## Actual retained evidence

- 14,686 records, 14,675 nonblank certified-bed counts, 11 blank. Reported daily average residents: 14,628 populated, 58 blank. Do not conflate these measures or infer occupancy without paired validation.
- 10,227 records carry valid chain IDs, 4,459 blank; 612 source-scoped groups. Earlier chain audit established full group-size parity and one reported name per group. Equal chain/PECOS affiliation tokens are only corroboration, not legal owner or property identity.
- Prior institutional qualification validates four field domains (special focus, survey-age flag, ownership-change flag and sprinkler category) on the same exact source pin. No additional row-level fields cleared.
- 808 geocoding footnotes are nonblank. Dictionary code 22 means ZIP-based coordinates; prior diagnostic recorded numeric footnote shape only, not the exact code. Therefore do not assert all 808 are ZIP centroids or upgrade precision.
- Standard-survey footnotes: 129 populated in cycle 1, four in cycle 2; code 29 is documented only in October text. Actual token membership not retained. No claim that these are confirmed risk-based surveys.
- Six star-rating / footnote pair diagnostics and 15 footnote shape distributions reused from [run 45841298990](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45841298990). [Chain audit 45826186143](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45826186143) and [institutional audit 45842903741](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45842903741) have the same nursing source checksum.

## Usage rules

[CMS technical details](https://data.cms.gov/provider-data/topics/nursing-homes/technical-details) distinguish quarterly staffing intensity, annual turnover, and case-mix adjustment. The July 2026 Five-Star guide distinguishes rating-specific health-survey counts from total citations, excludes Life Safety findings from star calculation, and uses two standard surveys with specified three-year complaint/infection-control windows. Keep rating scores, staffing rates, fines and deficiency counts separate. Clinical ratings are not property risk, and historical citation counts are not evidence of unresolved findings today. No new individual provider rows or location precision promoted. Contact remains presence only; legal business name remains restricted identity review. Existing UI and publication packs unchanged.

Next gate: exact dictionary bytes and source-specific domain validation, paired census/capacity and date/footnote diagnostics, geocode precision and institutional reuse review. Prior evidence is reused instead of a national rebuild. 
