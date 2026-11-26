# FY2024 financial report provider and fiscal period candidate audit

Completed 2026-11-26, run 45870156209, exact execution commit 4d725b2331371e13e4a90cad47ff13e16120719e. Both matrix jobs passed synthetic tests and pinned publisher source reconciliation; aggregate-only output. No Azure access or writes. No row-level output retained. No production or public data changes.

## Evidence and limits

The prior HCRIS direct-coordinate receipt supports 17 measures on matched report keys. The new candidate audit redownloaded the identical publisher ZIP and selected PUF bytes and reconciled the report-key cohort against that receipt. RPT candidate offsets were based on ResDAC's ordered hospital report fields (https://resdac.org/articles/medicare-cost-report-data-using-link-specifications-microsoft-access-when-importing-data); independent observed parity checked for both forms. All RPT records had 18 fields and six-character provider identifiers. Dates compared only if independently unambiguous under the existing parser; no locale assumption or missing-to-zero substitution.

| Scope | Hospital | SNF |
|---|---:|---:|
| Matched report keys, equal CCN | 4339 | 13772 |
| Unique matching directory CCN/state | 3618 | 13605 |
| Candidate reports satisfying all identity/period gates | 1502 | 9784 |
| Candidate provider records | 1498 | 9715 |
| Duplicate/overlapping period pairs among candidates | 0 | 0 |
| Unresolved fiscal dates (joint eligibility classification) | 2568 | 3904 |

The candidate cohort excludes unmatched source keys, unresolved periods, conflicting identity, and nonunique directory matches. No automatic newest report selection or inferred legal/property ownership. The absence of conflicts applies only to the eligible cohort, not all reports. Candidate report identity does not authorize individual financial attribution.

## Next gates

1. Obtain form-specific publisher RPT date-format and field-layout documentation; qualify ambiguous dates against those conventions with tests, not merely by choosing a date interpretation.
2. Qualify monetary units and worksheet definitions against the pinned publisher data dictionaries and form instructions. Keep asset balances, expenses, and current purchasing intent separate.
3. Verify approved historical report-level projection and reuse clearance; include all temporal/provenance metadata, preserve multiple reports, fail closed on unresolved links.
4. Only after those gates, consider a separately qualified facility financial view. Keep raw reports and private values out of Pages.

Receipt: research/hcris_provider_period_candidates_20261126.json. Source job links: https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45870156209.
