# Implementation status — 2026-11-25

Initial independent local development slice. The public repository contains source research, application code and tests, not commercial customer data or production infrastructure.

## Decisions
Use the standard library and SQLite for a runnable, zero-dependency local vertical slice. Retain the conceptual PostgreSQL/PostGIS + API + React architecture in the master plan; no production architecture decision is implied. Server-rendered screens avoid an initial JavaScript build dependency.

Official catalog documentation confirms IDs xubh-q36u, 4pq5-n9py, 23ew-n7w9 and r5ix-sfxw. Live payload retrieval in this environment was unavailable; adapters use explicit full CSV imports and independently declared release dates/row counts. The source research snapshots remain byte-identical. The new dialysis dataset is mapped separately.

No source has been live-ingested. Do not claim national population counts until import, row-count validation, current release confirmation and coverage audit. Public access is not automatic commercial reuse clearance.

## Next release gates
1. Retrieve full official releases; confirm CSV schemas, counts, dates, permitted reuse and original checksums; run first real national imports.
2. Independently validate provider record coverage and identifiers; resolve POS QIES/iQIES and CLIA national feeds.
3. Add hospital Form 2567 survey index, nursing home fire safety and penalties; preserve correction status.
4. Add normalized site/organization model, exact and reviewed crosswalks, geospatial API and national map.
5. Add equipment, environment, properties, procurement and service opportunity evidence classification. No scores before validation.
6. Production access control, tenant separation, deployment and monitoring require separate review.

This alpha intentionally does not expose an unauthenticated network server or automatically publish regulatory records. TowerSignal is unchanged.
