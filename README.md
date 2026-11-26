# FacilitySignal

Independent Pharm3r healthcare facility intelligence for the United States.

**Public research workspace:** https://jeremyhennessy.github.io/FacilitySignal/ (GitHub Pages). Searchable Care Compare provider projections, nursing citation aggregates, regional markets, capacity and historical national research evidence. The public site is not the full national SQLite database. The Python/SQLite application below remains local development only. Do not expose it to a network.

## Run

Python 3.11+; no third-party dependencies.

```sh
python facilitysignal.py init
python facilitysignal.py serve
```

Open http://127.0.0.1:8080. The UI and API read the same SQLite database. The source register is populated; no facilities or findings are seeded. The server is for local development only; do not expose it to a network.

## Build a validated national snapshot

```sh
python collect_cms.py --output data/cms-snapshot
python facilitysignal.py --db data/cms-snapshot/facilitysignal.sqlite3 serve
```

First full qualification: November 25, 2026, [run 45664651617](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45664651617). 48,004 provider records and 619,069 nursing home citation records, across 56 jurisdictions. Not unique properties or open violations. Local reproduction remains the durable path until approved persistent storage is connected.

## Load source snapshots

Obtain the full official CSV (not an Excel-edited or filtered export), verify its published date, row count, and permitted use; then import. Identifiers must remain strings.

```sh
python facilitysignal.py import-csv hospital /path/to/hospital.csv --release YYYY-MM-DD --expected-rows N
python facilitysignal.py import-csv nursing /path/to/nursing.csv --release YYYY-MM-DD --expected-rows N
python facilitysignal.py import-csv dialysis /path/to/dialysis.csv --release YYYY-MM-DD --expected-rows N
python facilitysignal.py import-csv nursing-health /path/to/deficiencies.csv --release YYYY-MM-DD --expected-rows N
python -m unittest discover -s tests -v
```

The seven provider datasets represent source-scoped provider records, not unique buildings. Two citation datasets provide nursing home health and fire citations, including historical and corrected findings; status is source-native. No clinical ratings are interpreted as facilities risk. No service leads generated yet.

| Adapter | Official catalog |
|---|---|
| hospital | https://data.cms.gov/provider-data/dataset/xubh-q36u |
| nursing | https://data.cms.gov/provider-data/dataset/4pq5-n9py |
| dialysis | https://data.cms.gov/provider-data/dataset/23ew-n7w9 |
| nursing-health | https://data.cms.gov/provider-data/dataset/r5ix-sfxw |
| nursing-fire | https://data.cms.gov/provider-data/dataset/ifjz-ge4w |
| home-health | https://data.cms.gov/provider-data/dataset/6jpm-sxkc |
| hospice | https://data.cms.gov/provider-data/dataset/yc9t-dgbk |
| rehabilitation | https://data.cms.gov/provider-data/dataset/7t8x-u3ir |
| long-term-hospital | https://data.cms.gov/provider-data/dataset/azum-44iv |

A CSV import checks the declared row count, required field mappings, identifiers and duplicate facility keys; exact duplicate finding rows are counted separately. One transaction replaces only its source's current snapshot. Older releases are rejected. Failed imports leave the existing snapshot intact. The audit log stores input hash, release and count, not the full source CSV; retain input originals externally where permitted. Row count checks alone cannot prove completeness; live retrieval and independent source validation remain required. Do not commit raw CSV, local DB, secrets or restricted records. The separate qualification workflow temporarily retains only the normalized nine-dataset public CMS database and audit manifest, for three days; public repository artifacts may be accessed by signed-in GitHub users.

## Current scope

- National directory (search, state/provider filters, pagination, detail)
- Nursing home deficiency search and exact-CCN link to nursing facility records
- Overview based on ingested source snapshots, no fake data
- Source register browser and imported-release history
- Read-only JSON endpoints: /api/overview, /api/facilities, /api/findings, /api/sources

Original source research and planning are under research/ and docs/. Source discovery is not ingestion. SQLite, Python standard-library server and server-rendered HTML are provisional zero-dependency development choices, not the final production stack. PostgreSQL/PostGIS, authenticated API, React UI, source workers, coverage review, ownership, equipment, environmental and procurement remain planned. No secure dynamic production deployment or additional cloud provisioning. The static public Pages deployment is separate. See docs/PUBLIC_INTELLIGENCE_20261126.md.


## Public release verification

Follow [AGENTS.md](AGENTS.md) for every public update. Run `python scripts/stamp_pages_assets.py --write` after changing the public JS or CSS; CI checks the versioned asset URLs. The live visual workflow must verify the normal public URL and its screenshots must be inspected before reporting completion. See [delivery incident and gate](docs/LIVE_VISUAL_RELEASE_20261126.md).
