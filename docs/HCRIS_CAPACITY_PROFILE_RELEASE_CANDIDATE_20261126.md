# Historical capacity public projection: narrowly scoped release candidate

Scope decision 2026-11-26: implement the owner's ongoing facility-profile development priority using the CMS selected FY2024 cost-report PUFs only. Catalog marks both PUFs free; retained source license is government works. CMS describes selected variables and permits reuse of government works with attribution/no implied endorsement. See:
- https://data.cms.gov/provider-compliance/cost-reports/hospital-provider-cost-report
- https://data.cms.gov/provider-compliance/cost-reports/skilled-nursing-facility-cost-report
- https://data.cms.gov/about
- https://data.cms.gov/resources/hospital-provider-cost-report-methodology

Separate from private Azure archival rights. Publication candidate includes only public PUF report ID, exact CCN/state, fiscal period, available beds at period end and (SNF only) available bed-days. No monetary data, private Blob access, raw reports, worksheet alpha values, patient data, contact details, or inferred ownership/equipment. Report-level grain is preserved; historical availability is not current certified beds or occupancy. The three-way source qualification is a consistency check, not independent original submissions. Coverage gaps are not zero.

Both deterministic files must exactly match the aggregate rehearsal receipts from run 45872218782 (hospital 546382 bytes, SNF 2434448 bytes; SHA pins in receipt). The existing pinned directory is independently rechecked; a changed directory or source byte hash fails closed pending requalification. No automatic regeneration from a newer publisher release. Initial build on an isolated branch only; both files are validated before committing; live app release requires candidate visual qualification and ordinary live URL evidence. No private archive or production storage changes.
