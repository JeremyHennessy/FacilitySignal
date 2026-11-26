# Care Compare infrastructure field review — 2026-11-26

Direct data-understanding continuation. Inspected main tree ec794de47aab686f80eebbb6f1e05a5c181ea111 and retained aggregate profiles from qualification 45822384234 (candidate 1a946bc562100c6497cf9426021e66000fd693d5). All seven provider headers inspected: 419 fields, 48,004 records. This is a targeted semantic review, not full dictionary qualification or new ingestion.

## Publisher evidence
- [Dialysis listing](https://data.cms.gov/provider-data/dataset/23ew-n7w9), October 28 release, confirms 7,471 rows and 146 columns.
- [Dialysis dictionary](https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/dialysis/DF_Data_Dictionary.pdf), Table 1, printed page 3 visually inspected. Extracted title says October 2026, extracted footer July 2026, rendered page footer January 2026. Revision discrepancy remains; these definitions are candidate semantics, not blanket current-version approval.
- [Nursing dictionary](https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/nursing_home/NH_Data_Dictionary.pdf), Table 2, page 9 visually inspected. Extracted October 2026 versus rendered June 2026 footer; rendered page also omits High Performing Icon present in extracted text. Do not claim exact current dictionary equivalence.

## Field decisions
| Source / original header | Meaning and observed evidence | Application rule |
|---|---|---|
| Dialysis / Chain Owned | Chain ownership OR management; 7,471 populated, two distinct tokens | Do not interpret as legal title; exact value frequencies pending |
| Dialysis / Late Shift | Reported shift beginning at or after 17:00; 7,471 populated, two tokens | Historical service scheduling, not live hours |
| Dialysis / # of Dialysis Stations | Reported station count; 132,479 total, 147 explicit zero, range 0–254 | Keep station units; zero requires cross-field investigation, not closure |
| Dialysis / Offers in-center hemodialysis | 6,959 yes, 512 no | Reported service, not current equipment inventory |
| Dialysis / Offers peritoneal dialysis | 4,067 yes, 3,404 no | Independent service flag |
| Dialysis / Offers home hemodialysis training | 2,411 yes, 5,060 no | Training service, not installed home equipment |
| Dialysis / Certification Date | Initial or subsequent certification date | Not necessarily opening date or accreditation |
| Nursing / Automatic Sprinkler Systems in All Required Areas | Dictionary distinguishes full, partial, absent and unavailable; 14,686 populated, three observed tokens | Preserve categorical value; exact counts and spelling pending; not an independent inspection |
| Nursing / Most Recent Health Inspection More Than 2 Years Ago | Snapshot survey-age indicator; 14,686 populated, two tokens | Not proof of an overdue legal obligation |
| Nursing / Provider Changed Ownership in Last 12 Months | Snapshot change indicator; 14,686 populated, two tokens | Not a deed or proof of current owner |
| Nursing / Special Focus Status | Program participant/candidate status; 527 populated, 14,159 blank, two populated tokens | Do not flatten participant and candidate or infer property risk |
| Long-term hospital / Total Number of Beds | Header-based candidate; 305 numeric rows, 21,765 total, six nonnumeric tokens | Publisher definition and six token meanings pending; do not combine with certified beds |

## Remaining qualification
Use checksum-pinned source data to produce exact aggregate token frequencies for these fields, cross-tab dialysis zero stations against service flags, and reconcile nursing sprinkler categories with fire citations without inferring current compliance. Review source-specific clinical measure denominators, confidence intervals and availability/footnote codes separately. No clinical ratings in environmental/property scoring without separately validated model. No new production mapping, UI, raw record publication or durable database integration in this pass.
