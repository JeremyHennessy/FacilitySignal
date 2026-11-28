# FS-043 national benchmark acquisition gate — 2026-11-28

The national benchmark is a separate release/grain from the already qualified 79,430 provider quality observations and 1,222 directory records. CMS publisher catalog metadata mirrored by the federal data catalog identifies nasn-k89k, modified 2026-08-12, released 2026-09-23, and its exact CSV distribution.

- https://catalog.data.gov/dataset/inpatient-rehabilitation-facility-national-data
- https://data.cms.gov/provider-data/dataset/nasn-k89k
- https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/inpatient/IRF_Data_Dictionary.pdf (September 2026 v7.0, Tables 5 and 8, pp. 9 and 17–19; note some page footer dates differ)
- https://www.cms.gov/medicare/quality/inpatient-rehabilitation-facility/irf-quality-public-reporting (September refresh and MSPB lag)

The dictionary documents 27 national measure codes: 12 rates, 12 counts of providers in comparative categories, and three standardized ratios/indexes. The national identifier is the literal Nation, not a provider CCN. The release date is not a reporting-window date; MSPB was explicitly not refreshed in September and must be treated separately. Do not sum these heterogeneous measures, compare an adjusted rate with an unadjusted benchmark without checking semantics, infer regulatory violations, or interpret missing as zero.

## Execution

Candidate 6ba4239952d9a4b11565b626b6a24fef11545c7b, run 46125924365, job 140920386458: four fixture tests passed; actual acquisition failed with RuntimeError, no audit artifact.
Candidate 79fca8226036445d305f3026343e8042fa73ae75, run 46125953372, job 140920481548: four fixture tests passed; stage-only diagnostic established HTTP 403 at initial publisher metadata request. The CSV retrieval and independent count steps were not reached. No raw or new permanent records, no source checksum, no qualification or public promotion. No automatic retry or alternative authentication. A publisher-documented archive path can be investigated separately with release and independent count evidence; do not circumvent access restrictions.

Existing source evidence and private archive are unchanged. PR #126 is not eligible for promotion as a qualified source. No Azure access, costs or UI changes.
