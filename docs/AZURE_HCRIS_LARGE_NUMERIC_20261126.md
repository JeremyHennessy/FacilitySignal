# Large FY2024 HCRIS numeric partition ingestion

Hospital source index: 19,440,697 numeric children; SNF source index: 13,769,223. Preserve source ordinals in consecutive, nonoverlapping ranges of at most 3,000,000 rows and 350 MB SQLite per shard. One publisher download and one numeric member pass per form; all shards are staged locally and the full member is reconciled against the pinned prior report index before any upload. Keep only exact numeric decimal text and bounded source-native coordinates; report references are not counted twice. Known structural-coordinate exceptions remain excluded and counted. Existing complete shards are verified and compared to full replay if needed. Every shard has an immutable exact receipt, and the full form completion requires all ranges and total row reconciliation. No numeric values interpreted as cost, capacity or financial units before a dictionary crosswalk. No alpha text or public changes. Existing storage is used; actual storage cost unverified. Count new observations, not new publisher releases.

Observed live source shape: hospital initial run 45861770583 failed before upload because the prior hospital index is an annual layout containing exactly 2024. The SNF index is a single-member layout. Select the exact receipt-defined index shape and its corresponding ZIP member group, verify annual scope and preserve all original validation. The correction is covered by an annual-layout fixture.

## Verified SNF completion

Run 45861770583, job 140054511175 passed all five shard SHA readbacks: 13,769,223 screened, 13,769,215 retained, eight coordinate exceptions excluded, no parent or numeric syntax exceptions. 1,182,690,816 payload bytes. Hospital annual-layout retry remains a separate run; do not claim its completion from SNF evidence.

## Verified hospital completion

Corrected run 45862301518, job 140056581197 passed all seven shard SHA readbacks: 19,440,697 screened and retained; no parent, coordinate or syntax exceptions; 1,646,231,454 payload bytes. SNF prior complete shards were also successfully recovered. All twelve FY2024 hospital and SNF scopes are individually verified. Consolidated ledger verification is separate.
