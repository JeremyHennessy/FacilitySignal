# CMS certification registry expansion

The public CMS catalog distinguishes a stable latest API alias and a version-specific API with the same temporal coverage. Use the version-specific API for independent row counts and the corresponding CSV/ZIP distribution. The legacy metadata catalog remains supported through March 31, 2027; migration to DCAT-US 3.0 is a tracked task.

```
python collect_registry.py --output data/certifications
python facilitysignal.py --db data/certifications/facilitysignal.sqlite3 serve
# To integrate with an existing validated Care Compare snapshot without modifying it:
python collect_registry.py --base-db data/cms-snapshot/facilitysignal.sqlite3 --output data/combined
```

All original release files are preserved in the local output raw/ directory with SHA-256 in the manifest; do not publish or commit these raw files. The application projection retains source-scoped provider identifier, name, address, provider type, certification/termination dates and status codes, plus a hash and ordinal for each source row. Original source fields outside the projection remain available in the retained local files; their semantic normalization is not complete. Exact duplicates and repeated provider identifiers are counted, not silently removed. Records can be historical or terminated. Never add these counts to the existing Care Compare provider counts; no inferred active status or cross-registry deduplication.

The certifications UI/API and ledger are isolated from existing provider/citation records. CI retains aggregate audit only. Full registry qualification and field mapping must pass before promotion. Source conditions and privacy review remain required before any additional data is redistributed.

Coverage ledger: research/coverage_status.json is an overlay of the unchanged original 176 entries; four original rows map directly to qualified Care Compare datasets, five additional datasets are recorded separately. Catalog/family rows are not marked complete merely because constituent files exist.
