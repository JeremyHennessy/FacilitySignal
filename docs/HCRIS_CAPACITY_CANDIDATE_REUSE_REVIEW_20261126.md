# Narrow selected PUF reuse review and capacity projection rehearsal

Both pinned FY2024 selected cost-report releases are explicitly marked free public-use files on CMS's catalog pages, and their retained catalog metadata points to the government-works license. CMS's open-data About page states reuse of government works does not require permission; attribute CMS and do not imply endorsement. USA.gov warns that not every work on a federal site is necessarily government-owned. This is a bounded source/field reuse assessment, not a legal opinion or a release authorization for the private Blob archive.

Official references:
- https://data.cms.gov/provider-compliance/cost-reports/hospital-provider-cost-report
- https://data.cms.gov/provider-compliance/cost-reports/skilled-nursing-facility-cost-report
- https://data.cms.gov/about
- https://www.usa.gov/government-copyright
- https://data.cms.gov/resources/hospital-provider-cost-report-methodology

First candidate deliberately excludes all monetary fields and the mixed SNF days/visits count. Include only the public PUF's report identifier, exact CCN/state, reporting period and historical available beds; SNF available bed-days also included. No raw ZIP, alpha text, private archive-derived values, patient data, owner names, personal contact details, inferred assets, or confidential data. Alpha/header observations are used transiently to validate PUF identity and period, not as public payload fields. Current certified capacity is a distinct source field and must not be replaced by historical reported availability. No aggregating across reporting periods.

Rehearse in memory, reconcile against the exact three-way and 17-measure receipts, and retain aggregate counts plus deterministic candidate SHA only. No row-level artifacts, Azure writes, Pages changes or promotion in this experiment. A separate release decision and browser qualification are required before any narrow public projection.
