# QCOR combined extension candidate — 2026-11-26

Existing ledger: ten QCOR sources FS-023 through FS-032, 628,073 previously
individually qualified source rows, 166,675 source-scoped survey event keys,
25,551 source-scoped provider keys (sums, not unique facilities), 217,065 memo
rows and 411,008 nonmemo tag rows. Their ten exact headers contain 155 columns
including 25 statement narrative columns. This candidate projects five raw
fields per source into four normalized values (provider key, event key, date,
row kind), with source and ordinal provenance. All other fields excluded from
this projection; the 25 narratives are intentionally not retained. Header counts
are not full value profiles or dictionary approval.

The earlier five-source extension run 45838315266 qualified 228,590 rows on
the retained nine-source Care Compare baseline (667,073 primary source rows).
Its temporary candidate was not retained, so the five exact releases must be
reprojected to test co-residence with the ten QCOR releases. The original CMS
artifact 15046953633 is reused, not redownloaded from the publisher. Expected
combined count: 1,523,736 primary source rows. No claim about the full 19-source
national database, canonical relationships, current findings, or commercial reuse.

The isolated workflow verifies exact source bytes, headers, field maps, nine
stable per-source audit outputs and the ICF publisher selector hash before
accepting data. It checks SQLite integrity, original table contents in both
directions, and the existing nursing citation day reconciliation. Only aggregate
audit evidence is uploaded. The candidate is deleted after qualification. No
new UI changes, persistent storage, approved commercial release, or promotion
is implied. Qualification is pending until the workflow and its evidence pass.
