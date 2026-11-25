# FacilitySignal — national product and engineering master plan

**Version:** 0.1 | **Date:** 2026-11-25 | **Status:** Planning proposal, not an approved implementation baseline

## 1. Mission and boundaries

A Pharm3r product for US healthcare facility, property, infrastructure, compliance, ownership and service-market intelligence. Coverage includes CMS and non-CMS facilities. Launch should provide national identity coverage with transparent source-specific coverage gaps. State and local enrichment will be uneven; never describe nationwide identity coverage as nationwide equipment, survey or property coverage. Prioritize non-patient facility and corporate records. No patient data, unnecessary personal information, serial numbers, internal plant locations or sensitive engineering details. Never portray a missing record as compliance or an inference as a confirmed problem.

Primary users: environmental and facilities service companies, engineering and equipment vendors, property and facilities managers, carriers/MGAs and healthcare real estate analysts. Clinical quality is contextual, not the primary product or a proxy for facility engineering risk. No automated insurance eligibility, denial or pricing decisions.

## 2. Verified research baseline

Local inspection of source register v0.2: 176 unique source IDs, 147 distinct URL strings, 79 documented access entries, 51 portals, 41 catalog entries, 3 candidates, 2 archives; 63 P0, 96 P1, 17 P2. All 176 ingestion statuses are not_tested. 175 reuse reviews pending, one specific restriction review required. 56 jurisdictions: 32 with initial sources, 2 authority/request only, 22 pending. These numbers describe the register, not production ingestion, independent datasets or current source accessibility. Its SHA-256 is fc9467d447607ca2352f995fb14a5e7574128b7bbf9f9b0b7f92d1835c5f5303. Preserve both research snapshots byte-for-byte.

## 3. Product navigation and interaction

1. Overview: total confirmed active facilities (with as-of date and source), counts by type, recent regulatory events, newly identified opportunities, map and coverage indicators. Do not invent counts; display no data until ingestion.
2. Facilities: searchable national table, filters for state/county, facility type, bed bands, parent system, ownership, inspection dates, deficiency categories, registered equipment, and source coverage. Search by facility name, city, ZIP, CCN, organizational NPI or system. Server-side filtering, sorting, pagination and query persistence in URL; table and map synchronized. Saved searches and export subject to role and source policy.
3. Facility detail: Summary, Inspections & Compliance, Water & Environmental, Infrastructure & Equipment, Property & Buildings, Ownership & Management, Contracts & Vendors, Financials & Capital Projects, Sources & History. Every displayed record includes date, provenance, status, match confidence where relevant. Distinguish active, historical, disputed and unknown.
4. Inspections: searchable national event feed, survey findings by regulatory tag, scope, severity and correction status; document excerpts only when authorized, otherwise original source link. Group inspection documents under surveys; preserve multiple findings per survey. Never duplicate a source-native event when refreshed.
5. Systems & Assets: only source-supported presence/type/count at permitted granularity; registration and inspection records separate from asset observations. Show coverage per asset class. No internal layout or sensitive infrastructure details.
6. Opportunities: service vertical filters, evidence, observed dates, freshness, source confidence, match confidence, inferred versus explicit versus historical contract. Capture saved accounts, notes, task assignment, exports when authorized. Do not label every deficiency as an actionable lead.
7. Organizations & Portfolios: browse operators, parent systems, managers and property owners separately; effective-dated relationships and portfolio rollups with duplicate prevention.
8. Contracts & Projects: historical awards, open solicitations, capital projects, acquisitions, closures and license changes. Explicit deadlines and procurement status; historical awards are not live bids.
9. Reports & Saved Lists: portfolio snapshot, service opportunity list, regulatory history, data coverage report; dated, auditable exports.
10. Admin/Data Intelligence: source catalog, actual endpoint, reuse review, schedule, last attempted/successful refresh, raw checksums, counts, schema drift, errors, coverage, match-review queue, classification rules, promotion history, access controls and manual correction audit.

UI direction: practical enterprise analytical interface, restrained brand identity, compact data tables, accessible keyboard navigation, responsive layouts, clear source and date labels. No approved visual baseline yet. Reuse TowerSignal patterns only after actual approved files/screenshots and dependencies can be reviewed. No changes to TowerSignal production.

## 4. Conceptual model (not a finalized migration)

Use durable internal UUIDs, source-native keys with namespace and jurisdiction, effective dates, recorded dates, and audited reversible merges. A provider is not a building. Multiple providers can occupy one building; one provider may operate multiple sites. A campus may contain several buildings and parcels. Corporate ownership is distinct from property ownership and facility management. Use relationship tables rather than forcing one parent per site.

| Logical entity | Purpose |
|---|---|
| organization, organization_identifier | Legal entities, operators, parent systems, property owners, contractors; source-scoped identifiers |
| organization_relationship | Ownership, management, affiliation, contractual relationships; effective dates and provenance |
| facility, facility_identifier | Licensed/certified operational identity and source-native IDs; status and type history |
| facility_site, site, campus, building, parcel | Physical location graph with crosswalks, normalized address, geocoding quality, coordinates as permitted |
| facility_organization_role | Operator, licensee, parent, manager and other evidence-supported roles |
| property_organization_role | Owner, manager and other roles for property/building |
| registration, certification, license | Regulatory record with scope, issuer, status, issue/expiry dates and source key |
| inspection, finding, enforcement_action | Separate survey event, citations/deficiencies and penalties/orders; dates, source-native severity and correction status |
| asset, asset_observation, asset_inspection | Confirmed registered assets versus observed/reported counts, proposed equipment and inspections; no inferred individual asset creation |
| environment_record, water_system_link | Environmental permits, observations and enforcement, regulated on-site water system versus external supplier |
| solicitation, award, capital_project | Procurement and projects with status, deadline, supplier, dates and recipient/location relationship confidence |
| facility_measure, finance_record | Source-specific capacity, financial and quality measures with units and period |
| service_classification, opportunity | Versioned evidence-to-service mapping, signal type, confidence, freshness, workflow state |
| source, source_endpoint, source_policy, source_release, raw_object, ingestion_run | Source governance, provenance, immutable releases and ingest audit |
| source_record, entity_link, review_case | Source-native data keys, normalized linkage, confidence, human adjudication and merge/split history |
| tenant, user_role, saved_list, note, audit_event | Segregated tenant-specific business workflows |

Every source-supported fact carries source ID, source record key, original URL or release pointer, publication/observation date where available, fetched_at, parser version, link status and provenance. Preserve source-native values and units. Distinguish observed time, effective time, and ingestion time. Document licensing limitations; when raw retention or redistribution is prohibited, retain only permitted metadata and pointers. Do not store secrets in source registers.

## 5. Architecture proposal

Local-first development: Python adapters and tests, PostgreSQL with PostGIS and indexed search as an initial design, typed HTTP API, React/TypeScript browser UI, object storage for permitted raw snapshots, and separate scheduled/queued ingestion workers. For development, local containers with non-production config and small fixtures. At production scale, prefer existing approved Pharm3r infrastructure where compatible: Azure Blob for object storage, Azure Static Web Apps or equivalent approved front end, managed PostgreSQL and a suitable worker/API host. This is a proposal; actual provider, credentials, costs, regions, resource names, authentication and repository visibility must be confirmed after reviewing the current environment. No cloud spending or resource creation approved by this plan. Do not reuse TowerSignal production credentials or databases by default. Do not require a new search cluster before benchmarking Postgres. Do not deliver all national records in one browser JSON payload.

Data path: discovery -> policy review -> fetch -> permitted raw snapshot/checksum -> parse -> schema validation/quarantine -> normalized staging -> deterministic identity links -> candidate entity resolution/review -> canonical tables -> search/read models -> release validation -> atomic active-release switch -> UI/API.

Maintain source-specific adapters with documented formats and refresh cadence; implement per-source checkpointing, bounded retries, conditional fetching, respect rate limits/robots/terms and avoid prohibited crawling. Track full snapshots versus incrementals, withdrawals/deactivations, record changes, failed batches, schema versions, expected coverage, and source-native stable IDs. A failed refresh must retain last known good data and expose staleness. Do not mark a run complete until its checks pass. No destructive production tests. Large imports run asynchronously in the eventual worker service, not in this chat.

Search and performance: server-side cursor pagination, geography and identifier indexes, text search, bounded queries, map clustering, query-derived totals with explicit date/source scope. Validate performance against representative data before committing capacity/SLOs. Separate public/source-permitted facts from tenant-private notes and restricted source content. Role-based access, tenant boundary checks, read audit, encrypted transport, managed secrets, retention and backups; no patient data.

## 6. Entity resolution and confidence

Deterministic: source-native unique key within namespace; validated CCN crosswalks, state license + issuer/type, CLIA identifiers, organizational NPI; identifiers describe different regulated scopes and must not be collapsed just because their addresses match. NPPES organization records can include billing/non-service addresses; confirm practice location and operational status. Address and name normalization, suite/campus parsing, postal/geographic consistency, and validated geocoding support candidates, not automatic universal merges. Block competing identifiers, different units, shared addresses and ambiguous subsidiaries. Human-review uncertain matches; preserve source records and link revisions. Label probabilistic matches and do not expose low-confidence links as facts. Facility/organization/site counts remain separate. Test against co-located distinct providers, multi-site providers, acquisitions, closed sites, renames, cross-state chains and shared parcels.

## 7. Initial ingestion order (proposed)

A. National identity: FS-001 QIES, FS-002 iQIES, FS-003 CLIA, FS-006 Hospital General Information, FS-008 SNF enrollment, FS-009 HRSA service sites. FS-004 NPPES and FS-005 PECOS enrichment after sample and location-scope tests; stage the large NPPES download rather than load the whole file in memory.
B. Inspection core: FS-033 nursing home deficiencies, FS-034 inspection dates, FS-020 hospital Form 2567 index and permitted document retrieval; resolve exact sources for FS-035 fire deficiencies and FS-036 penalties. Use source-native inspection dates/tags, not downloaded dates. Start deterministic rules; keep original evidence and measure extraction errors on manually reviewed documents before scaling.
C. Ownership: FS-045 hospital owners, FS-047 SNF owners, FS-051 AHRQ system compendium; validate historical vs current relationships.
D. Federal crosswalk: FS-062 EPA FRS, FS-070 OSHA inspections, FS-157 drinking-water systems, then exact ECHO/SDWIS/RCRA/NPDES datasets; ensure match and permit scope. Hospital's own PWS is not the same as utility serving it.
E. Procurement: FS-060 USAspending; FS-058 SAM opportunities after authorized API access and policy checks; preserve explicit status and award recipient vs service site. Add contract renewals as hypotheses, not facts.
F. Demonstration enrichment: FS-105 MN boilers, FS-108 OH radiation registrations, FS-112 TX elevator data, FS-113 FL inspection extracts; FS-164 PA VA campus water reports for bounded evidence. Add NY TowerSignal-compatible sources only after separate reuse review and matching validation. Do not restrict the base app to these states.

This is an ordered qualification queue, not a claim these endpoints are usable. Each adapter requires exact release/endpoint and sample, schema keys, reuse permissions, test fixture, expected update cadence and source limitations. All 176 entries remain in research register until qualified, plus ongoing state and municipal discovery. Prioritize federal base even when state discovery incomplete.

## 8. Commercial signal design

Use two separate measures: service opportunity priority and evidence reliability; optionally a regulatory exposure summary, not a clinical safety or insurance pricing score. Do not reuse TowerSignal score weights without validation. Evidence reliability is lowest of source applicability, linkage quality, extraction confidence and freshness where relevant. Opportunity types: open explicit solicitation; documented finding or enforcement; documented inspection/registration due date (when applicable); documented planned capital project; historical service award; inferred need from asset/inspection evidence. Track status open, corrected, closed, expired, unknown; suppress closed or resolved findings from active need lists unless separately supported. A confirmed asset alone is not proof of maintenance need.

Start with qualitative ranked categories, reasons and source links. Develop numeric model after manual relevance labels, review precision/coverage by service and jurisdiction, tune and version weights, document missingness. Use no clinical/patient identifiers or demographic proxies in risk scoring. No automatic underwriting decision. Deduplicate findings shared by sources and avoid penalizing better-reporting jurisdictions. Allow users to see exact inputs and distinguish fact from inference.

Service taxonomy: water management, Legionella, water treatment, sterile processing water, dialysis water, environmental testing, waste, HVAC/ventilation, plumbing/backflow, fire/life safety, elevator, power/generators, medical gas, biomedical equipment, cleaning, building envelope, remediation, renovation, energy management, property management. Expand with observed evidence, not speculation. Generic deficiency cannot establish equipment presence or unperformed service.

## 9. MVP and release gates

First useful release: national facility directory and search; facility details with source identifiers, locations, facility types and ownership where verified; actual nursing home/hospital inspection evidence where supported; national map; evidence-linked service opportunity list; state/source coverage matrix; admin run status. Start with real public data, not invented UI counts. Non-CMS/state-only facility types are incremental and explicitly labeled. Login/tenant segregation and authorized export before customer access.

Acceptance gates:
- Source policy and access: reviewed permission/terms, endpoint responds, current release and schema recorded, provenance on every displayed finding.
- Data quality: source-specific record reconciliation, fixture tests for idempotent reimport, stable IDs, no silently dropped rows, duplicate/orphan checks, quarantined bad rows, verified dates and status. Baseline counts by provider type/state compared to official release rather than assumed totals. DC/territory coverage documented separately.
- Matching: independent stratified manual review before probabilistic auto-linking; document sample sizes, precision, ambiguity and exclusions. No uncertain merge displayed as certain.
- User flows: search by name/CCN/state, inspect facility profile, open source evidence, filter water/fire/HVAC findings, view ownership where available, export permitted rows and save list; verify pagination, back navigation, filters, keyboard access, mobile/desktop states and permissions.
- Operational: a forced refresh failure retains previous release; rollback tested; backups restore in nonproduction; verify actual running UI against published data; disclose stale/missing source state; no production credential leakage. No deployment or public commercial use until approval and reuse review.

## 10. Delivery sequence and repo layout

Milestone 0 (current): preserve research, architecture, backlog, no repository creation.
Milestone 1: repository/visibility confirmed; local dev scaffold, migrations, source registry, CI tests, qualified small national identity sample, repeatable import. No cloud setup needed.
Milestone 2: national identity import, coverage QA, search/map and facility detail against real data.
Milestone 3: nursing home findings plus hospital survey index and permitted documents; ownership, service taxonomy and evidence UI; first customer-ready pilot after acceptance gates.
Milestone 4: national environmental/procurement enrichment and state equipment pilots; review opportunity relevance and linkage quality.
Milestone 5: expand state-by-state and municipal records, properties, capital projects, vendors and portfolio monitoring; controlled releases and ongoing freshness audits.

Proposed repo structure (not yet implemented):
```
apps/web/                # React/TypeScript UI
services/api/            # typed query API
services/ingestion/      # source adapters and jobs
packages/data-contracts/ # shared schemas and taxonomy
infra/                   # local development, later approved deploy config
migrations/              # versioned database schema
research/                # source snapshots, coverage research, policies
config/sources/          # qualified endpoints; no secrets
fixtures/                # small permitted test fixtures
tests/                  # ingestion, linkage, API, UX and security tests
docs/                   # charter, decisions, acceptance, runbooks
```

## 11. Decisions still open

Repository name FacilitySignal and product direction are owner-endorsed in chat; repository visibility, formal name/trademark availability, hosting plan, auth strategy, paid services, domain provisioning, source-specific permissions, exact data refresh frequency, pilot customers and scoring thresholds remain unapproved. Proposed stack and UI organization may change after reviewing actual TowerSignal infrastructure. No live app, ingestion, tests, repo or cloud resources were created by this planning pass. The owner reported GitHub problems; their status was not independently investigated because this task is local planning.
