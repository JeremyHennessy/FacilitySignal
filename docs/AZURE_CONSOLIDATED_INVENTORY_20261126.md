# Consolidated private Azure archive checkpoint — 2026-11-26

Evidence baseline: `05609b333c653ded35babb76684ea5e5aedb5229`. Individual main-branch completion receipts and previously verified recovery runs establish **9,622,578 source observations across 43 publisher releases** plus **23,520 derived identity candidates**, kept separate. 84 payload files, 1,926,896,232 payload bytes including the derived candidate layer. These are not unique facilities, and do not include nested taxonomy values as additional source rows. Counts cover only explicitly pinned complete archives; they are not an account-wide storage or billing total.

| Layer | Observations | Evidence |
| --- | ---: | --- |
| national | 1904060 | [45847538263](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45847538263) |
| extension | 865809 | [45848914611](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45848914611) |
| hcris-hha-2024 (d3bf63b5d629; publisher) | 4791697 | [45850246524/140014524747](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45850246524/job/140014524747) |
| hha-organizational-ownership (75f6de0bde69; publisher) | 21734 | [45850540913/140015646754](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45850540913/job/140015646754) |
| hha-selected-cost-2024 (3e864b52252b; publisher) | 10970 | [45851139665/140017590258](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45851139665/job/140017590258) |
| hospice-organizational-ownership (23de741ded45; publisher) | 18763 | [45851139665/140017590334](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45851139665/job/140017590334) |
| nppes-monthly (c5a34fba9b2e; publisher) | 1990237 | [45850246524/140014524795](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45850246524/job/140014524795) |
| nppes-weekly (080d77078615; publisher) | 6417 | [45850246524/140014524694](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45850246524/job/140014524694) |
| nppes-weekly (cfdac80d3056; publisher) | 6264 | [45850246524/140014524694](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45850246524/job/140014524694) |
| nppes-weekly (d0e73f9d00ee; publisher) | 6627 | [45850246524/140014524694](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45850246524/job/140014524694) |
| pecos-nppes-identity-candidates (faf0318d9f32; derived) | 23520 | [45851929487/140020318991](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45851929487/job/140020318991) |

Machine-readable aggregate and per-file pins: `research/azure_archive_inventory_20261126.json`. The new workflow performs an independent read-only metadata/ETag and completion-receipt reconciliation on trusted main, with optional manual full SHA-256 recomputation. Original payload-byte verification is evidenced by the historic receipt runs. No secret access outside the existing environment, source downloads, payload overwrites/deletes, pointers or Pages changes. Live execution is not asserted until the new workflow completes. Pinned scope deliberately excludes future refreshes, unqualified archives, incomplete uploads, and private objects outside listed releases. Reuse and source-specific semantic review remain pending. Next ingestion priority: qualify HHA and hospice enrollment releases and crosswalk their separate organizational-owner layers; expand private source coverage and the weekly source-specific refresh policy before any new public pack publication.
