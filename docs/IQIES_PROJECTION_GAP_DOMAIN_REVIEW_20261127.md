# iQIES original projection gap — aggregate domain reconciliation, 2026-11-27 UTC

Reconciled 164 populated aggregate fields outside the original November 26 baseline using the exact pinned iQIES raw field profile and semantic crosswalk. The underlying profile contains 100,334 source records; no new source download or row-level access. The receipt binds the exact evidence blobs and records each original ordinal, category, disposition and conflicting provider scopes. This is an aggregate evidence screening gate, not a fresh source qualification or application approval.

| Disposition | Fields |
|---|---:|
| other_review | 19 |
| bounded_domain_mapped_code | 16 |
| scope_conflict | 20 |
| bounded_domain_boolean | 50 |
| bounded_domain_fte_decimal | 36 |
| bounded_domain_count_integer | 14 |
| blocked_metadata | 5 |
| domain_incomplete_mapped_code | 2 |
| domain_incomplete_fte_decimal | 2 |
| Total | 164 |

Bounded-domain categories require every populated scope to reconcile its observed nonmissing values to the previously recorded yes/no, mapped code or nonnegative numeric counts. Numeric screening is not validation of units, magnitude, additivity, or integer precision. The entire field is withheld from this candidate category if any scope has out-of-scope nonblank values, unresolved nonblank scope, or applicability conflict; a documented scope may later qualify independently. Blank and explicit missing states remain distinct from zero and no. All five existing semantic blocks take precedence. Other fields require source-text, date, identifier or scope-specific review. No new display fields, contractor links, installed equipment, current operational claims or commercial publication authorization.

Examples: pharmacy service has populated HHA values despite an ASC-only dictionary scope; total beds has populated NH values outside the stated ICFIID/PRTF scope. Speech therapy and vocational guidance lack reconciled mapped-code counts. These are investigation targets, not source error conclusions. The next step is scope-specific selection and review of the bounded candidates against the existing runtime projections and source reuse rules, not automatic publication.

Evidence: [field-level receipt](../research/iqies_projection_gap_domain_review_20261127.json). Tests independently reconstruct the classification and pin source evidence, with negative controls for precedence and incomplete domains.
