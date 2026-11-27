# FacilitySignal guide

Documentation checkpoint: November 27, 2026. Public route descriptions were checked against [repository revision `3d9871cb`](https://github.com/JeremyHennessy/FacilitySignal/tree/3d9871cbe52ce8f561e79beff6985de0925af293) and its data manifests. This is not a new visual release verification.

## Start with the question you are trying to answer

| Question | Start here | What the evidence means |
| --- | --- | --- |
| Which providers are reported in this market? | [Advanced facility search](https://jeremyhennessy.github.io/FacilitySignal/#advanced) or [Market explorer](https://jeremyhennessy.github.io/FacilitySignal/#geography) | A provider source record is not necessarily a unique building or a current operating site. The map shows jurisdiction counts, not site pins, risk rates, or population-adjusted coverage. |
| Which research pathway applies to my work? | [Industry research](https://jeremyhennessy.github.io/FacilitySignal/#industry) | Six pathways link to provider evidence or national aggregates. A state selection does not filter national aggregate pages unless the destination explicitly says so. These are research starts, not customer leads. |
| Can I compare provider records? | [Saved facility portfolio](https://jeremyhennessy.github.io/FacilitySignal/#saved-portfolio) | Compare named source records and explicitly cleared fields. A comparison does not establish common ownership, a shared site, or a customer account. |
| What capacity is actually reported? | [Capacity explorer](https://jeremyhennessy.github.io/FacilitySignal/#capacity) | Preserve the publisher's unit, release, measured scope and missingness. A blank is not zero. Do not use another program's count to fill a blank. |
| What did a regulator report? | [Nursing home citations](https://jeremyhennessy.github.io/FacilitySignal/#citations) and [Compliance research](https://jeremyhennessy.github.io/FacilitySignal/#compliance-research) | Historical citations do not establish an open violation or current compliance. A missing record does not imply compliance. |
| Can I verify equipment at a particular place? | [Equipment and environmental research](https://jeremyhennessy.github.io/FacilitySignal/#equipment-environment); for a specific pilot see [Minnesota boiler research](https://jeremyhennessy.github.io/FacilitySignal/#industry?state=MN) | The public app does not provide a national installed-equipment inventory. Minnesota's guide leads to a separate state certificate lookup, not a CMS-to-equipment match. Confirm the exact campus and address. |
| Is a source live in the app or archived? | [Source register](https://jeremyhennessy.github.io/FacilitySignal/#sources) and [Data intelligence](https://jeremyhennessy.github.io/FacilitySignal/#data-evidence) | Follow the release and evidence links. A discovered source, a qualified snapshot, an archived payload and an approved public projection are separate states. |

## What is available today

- **Public GitHub Pages:** the [directory manifest](../web/public-directory/manifest.json) reports **48,004 provider records across 56 jurisdictions** from seven Care Compare sources, plus public summaries derived from **619,069 historical nursing citation source rows**. The totals are not unique sites, open issues, or all US healthcare entities. Other public views may expose selected, separately reviewed evidence; they do not expose the full SQLite archive.
- **Private Azure:** [archive inventory reconciliation](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45900897912) covered **216 pinned files and 57 publisher releases by metadata**. An [earlier full SHA-256 readback](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45882881556) covered **212** files. These are archive checkpoints, not live-public freshness claims. The [coverage ledger](../research/coverage_status.json) keeps source observations, samples, derived candidates and public clearance distinct.
- **Local Python/SQLite:** separate development workflow; keep loopback-only. It is not a production database/API behind GitHub Pages.
- **Refresh:** the [workflow](../.github/workflows/azure-weekly-refresh.yml) is configured for Mondays at 11:17 UTC and also supports pushes and manual dispatch. Its refresh step checks publisher metadata and existing private candidates; it does not guarantee new retained bytes or automatic Pages publication. Verify trigger, result, release and public deployment separately before describing a source as refreshed.

## Review rules for each new source

1. Record publisher, release, observation time, reporting period, what each row describes and the denominator if known. Do not silently substitute a roster count for a measure denominator.
2. Record count/hash/disposition and whether the material is merely discovered, screened, fully validated, retained, or public. Label legal/rights review and privacy status separately.
3. Separate certification number (CCN), enrollment identifier, organization identity, physical site and operating status. Treat address-only agreement and same-CCN address formatting differences as candidates, not automatic links.
4. Distinguish blank/unavailable, withheld, not applicable, reported no and known zero. For example, [the approved hospice and rehabilitation pack audit](https://github.com/JeremyHennessy/FacilitySignal/commit/5b9665b7223af730c4f6ae528c26efb83fbe400e) found 7,692 blank capacity fields, not zero capacity.
5. Prioritize national CMS and related federal datasets; add state and local sources where they fill a defined gap. Keep raw/restricted rows out of Pages, use the [release gate](../AGENTS.md) for any public visual change, and preserve historical receipt documents.

Current priority: qualify national enrollment and physical-site evidence before widening facility-level joins. Show unknowns instead of overriding them with address matches, private totals, or source-wide averages.
