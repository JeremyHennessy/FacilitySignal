# FacilitySignal

Independent Pharm3r healthcare facility intelligence for the United States. Development alpha, local only.

## Run

Python 3.11+; no third-party dependencies.

```sh
python facilitysignal.py init
python facilitysignal.py serve
```

Open http://127.0.0.1:8080. The UI and API read the same SQLite database. The source register is populated; no facilities or findings are seeded. The server is for local development only; do not expose it to a network.

## Load source snapshots

Obtain the full official CSV (not an Excel-edited or filtered export), verify its published date, row count, and permitted use; then import. Identifiers must remain strings.

```sh
python facilitysignal.py import-csv hospital /path/to/hospital.csv --release YYYY-MM-DD --expected-rows N
python facilitysignal.py import-csv nursing /path/to/nursing.csv --release YYYY-MM-DD --expected-rows N
python facilitysignal.py import-csv dialysis /path/to/dialysis.csv --release YYYY-MM-DD --expected-rows N
python facilitysignal.py import-csv nursing-health /path/to/deficiencies.csv --release YYYY-MM-DD --expected-rows N
python -m unittest discover -s tests -v
```

The first three datasets represent source-scoped provider records, not unique buildings. The fourth provides nursing home citations, including historical and corrected findings; status is source-native. No clinical ratings are interpreted as facilities risk. No service leads generated yet.

| Adapter | Official catalog |
|---|---|
| hospital | https://data.cms.gov/provider-data/dataset/xubh-q36u |
| nursing | https://data.cms.gov/provider-data/dataset/4pq5-n9py |
| dialysis | https://data.cms.gov/provider-data/dataset/23ew-n7w9 |
| nursing-health | https://data.cms.gov/provider-data/dataset/r5ix-sfxw |

A CSV import checks the declared row count, required field mappings, identifiers and duplicate facility keys; exact duplicate finding rows are counted separately. One transaction replaces only its source's current snapshot. Older releases are rejected. Failed imports leave the existing snapshot intact. The audit log stores input hash, release and count, not the full source CSV; retain input originals externally where permitted. Row count checks alone cannot prove completeness; live retrieval and independent source validation remain required. Do not upload raw CSV, local DB, secrets, or restricted records to GitHub.

## Current scope

- National directory (search, state/provider filters, pagination, detail)
- Nursing home deficiency search and exact-CCN link to nursing facility records
- Overview based on ingested source snapshots, no fake data
- Source register browser and imported-release history
- Read-only JSON endpoints: /api/overview, /api/facilities, /api/findings, /api/sources

Original source research and planning are under research/ and docs/. Source discovery is not ingestion. SQLite, Python standard-library server and server-rendered HTML are provisional zero-dependency development choices, not the final production stack. PostgreSQL/PostGIS, authenticated API, React UI, source workers, coverage review, ownership, equipment, environmental and procurement remain planned. No production deployment or cloud provisioning.

