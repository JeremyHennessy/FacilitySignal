# Financial measure and period qualification — continuation, November 26

Three-way candidate audit: pinned RPT header, publisher-selected PUF and S-2 Part I alpha worksheet observations. The CMS dictionaries map CCN, state and dates to hospital S2 Part I rows 3, 2 and 20; SNF rows 4, 2 and 14. The form-specific electronic reporting specifications explicitly prescribe MM/DD/YYYY for beginning/end fiscal dates (hospital Table 3 p. 40-729 and SNF Table 3 p. 41-518). The published PUF or RPT may have a different export representation: accept only ISO or documented MDY and require all three normalized observations to agree, with unique exact directory CCN/state and FY2024 beginning date. No resolution by guessing alternate locales. If worksheet values are absent, duplicated, or incompatible, exclude; report counts, not raw values.

Sources:
- https://data.cms.gov/sites/default/files/2024-03/9756088d-5280-4090-80b9-449d31ef25a3/Cost%20Report%20Data%20Dictionary%20Update.pdf
- https://data.cms.gov/sites/default/files/2023-12/Skilled%20Nursing%20Facility%20Cost%20Report%20Data%20Dictionary_508.pdf
- https://www.cms.gov/Regulations-and-Guidance/Guidance/Transmittals/Downloads/R7P240s.pdf
- https://www.cms.gov/Regulations-and-Guidance/Guidance/Transmittals/downloads/R2P241.pdf
- https://resdac.org/articles/creation-fiscal-year-cost-report-files

Measure semantics: historical number of beds is available beds at period end, not present certified beds. SNF bed-days are period-weighted available capacity; total days includes visits where applicable, so do not compute occupancy using this aggregate without a narrower measure. Salary/overhead are accounting-book expenses; contract labour is scoped to direct patient care and top management per CMS dictionary. Monetary measures are report-grain and units/scaling not yet established by numeric equality or integrality. No conversion, totals, facility attribution, or publication. Audit only numeric domain shapes across each complete pinned PUF, not values.

Prior receipts remain immutable. The new audit does not change public app, Blob, or production. Reuse and publication review remain separate.
