# CLIA certificate semantic audit — 2026-11-26

Qualified source: Q3 2026 Provider of Services File — Clinical Laboratories; 686,058 rows, 103 columns, SHA-256 b7b7dce68abec2ad69b6c3378ff14e0b1c4e12f5dda433d12db2cf8eb4c5b1bf. Source period 2026-07-01/2026-09-30. Qualification: [run 45831429985](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45831429985), job 139948901884, commit a598ca8c2686c42dc0670db135fb03881ecbf75b, success. Exact historical 2023 layout and crosswalk artifact hashes recorded in `research/clia_certificate_semantic_audit_20261126.json`. All 103 field reviews retain source names, historical definitions and domain evidence. The historical dictionary is not blanket current-version approval.

## Findings

- Both termination columns agree exactly for this release: 299,345 literal 00, 386,615 other historically documented codes, 98 code 95. Code 95 remains unmapped after a targeted CMS documentation search; no assumed meaning. Do not infer current operations or certificate validity from 00.
- Within literal 00: 244,230 waiver, 22,034 provider-performed microscopy, 15,821 accreditation, 15,237 compliance, 2,023 registration records. Facility-type codes distinguish physician offices, pharmacies, nursing facilities, hospitals, independent laboratories, surgery centers, dialysis facilities and other categories. They do not identify unique physical sites. Historical code 18 label is incomplete in the extraction.
- Certificate effective and combined termination/expiration dates parsed as compact calendar dates on all rows. Relative to September 30, 2026, 1,180 code-00 records have termination/expiration on or before that date; 7,149 have an effective date after it. One effective date follows the combined termination/expiration date. The combined date cannot disambiguate termination from expiration. These are diagnostics only.
- All seven observed accreditation confirmation patterns require the application X flag and a populated match date in this release. Distinguish declaration, confirmation, and date; organization counts overlap. No present-day accreditation claims.
- There are 686,058 distinct registry identifier tokens; 260,718 populated affiliation reference occurrences, of which 260,315 match registry IDs and 403 do not; two self-reference occurrences. No verified ownership, affiliation, or unique-premises claim.
- Multisite flags/counts: 38,575 Y/positive, 46 Y/zero, 190 N/positive, 647,247 N/zero. Flag/count discrepancies require review and are not proved source errors.
- The 2026 procedures guide was text-reviewed; its oversized PDF prevented web screenshot retrieval. No visual inspection of that guide is claimed. Historical layout retained separately.

## Public projection

Only six explicitly selected national aggregate tables are added using the existing public intelligence renderer. No individual laboratory records, identifiers, exact dates, contact details, volume sums, equipment, or operational inferences are published. Existing UI, asset versions and previous evidence groups are unchanged. Candidate and ordinary live URL visual release gates are required before claiming the application update complete.

Sources: [CMS methodology](https://data.cms.gov/resources/provider-of-services-file-clinical-laboratories-methodology); [CMS 2026 CLIA procedures guide](https://qtso.cms.gov/system/files/qtso/CLIA_116_Cert_PG_12.4.7.1_FINAL_0.PDF).
