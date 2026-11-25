# CMS national bulk ingestion (candidate)

Official source: https://data.cms.gov/provider-data/data.json and dataset metastore.
Use versioned full CSV distributions, official release dates, and independent API counts.
The collector stages all requested datasets, compares metadata and API counts before/after download, checks file SHA-256 and import counts, rejects failed batches, and writes a separate new SQLite snapshot with a manifest. Exact duplicate citation rows are tracked; provider IDs are source-scoped. Health and fire safety citations remain separate; they do not constitute open violations or inferred service needs. Unmatched historical nursing home citations are retained and counted.

```
python collect_cms.py --output data/cms-snapshot
python facilitysignal.py --db data/cms-snapshot/facilitysignal.sqlite3 serve
```

Scope: hospital, nursing home, dialysis, home health, hospice, inpatient rehabilitation, long-term care hospital; nursing home health and fire citations. Source register v0.2 remains unchanged. No patient-level records are imported. Raw downloads and derived SQLite snapshot stay local/ephemeral, not committed. CI retains aggregate manifest only (no row-level records). Data redistribution and production publishing require review.

Status: branch candidate; live full-snapshot tests required. This is not a deployment, and the existing main branch remains unchanged until tests pass.
