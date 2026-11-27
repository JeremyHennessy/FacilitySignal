# FacilitySignal continuous product development charter

Owner directive received 2026-11-26. This supersedes prior FacilitySignal layout-preservation constraints for ordinary reversible product development, not security, data integrity, publication permissions, or verified functionality.

## Product mandate

Build a unified national healthcare facility intelligence platform for facility operators, property managers, environmental/water/infection-prevention service firms, compliance professionals, insurers and MGAs, sales teams, researchers and portfolio analysts. Organize around user objectives: discover facilities and markets, examine facility/organization evidence, compare and manage portfolios, understand regulatory history, research operational infrastructure and commercial markets, monitor meaningful changes, and trace findings to sources.

Regularly reconsider the product as if built from scratch today. Remove, merge or redesign redundant pages when useful; retain effective behavior, deep links and recoverable versions until equivalents are qualified. Do not create a page for every dataset. Use new data to improve meaningful intelligence and progressive disclosure.

## Non-negotiable evidence boundaries

Source -> collection -> processing -> entity resolution -> analysis -> application -> presentation. Distinguish source record, physical site, legal entity, candidate relationship, confirmed relationship, and national aggregate. Preserve original release, grain, provenance, missingness, applicability, units, status and time semantics. Do not equate clinical quality with building risk, historical citations with open violations, service flags with equipment installation, cost reports with purchases, or affiliation with legal title. Do not release restricted rows or change access/security merely to expand features. No unapproved paid or private-storage architecture changes.

## Development and acceptance

Inspect main, live site, latest ingestion and field utilization evidence. Prioritize user value, implement directly in a recoverable branch, test actual data and all affected user interactions, deploy via existing GitHub Pages, verify normal live URL with exact asset checks and actual desktop/tablet/mobile Chromium screenshots, visually inspect meaningful changes, correct defects, retain qualification evidence and update priorities. Do not count a commit, recommendation, or queued job as success. Preserve ongoing concurrent data work. If live verification or publisher/reuse clearance is blocked, explicitly report the limitation.

## First architectural release

Rollback baseline: main 47f2d9d12c1a56f80b5f0a16409a602abc9c804d; preceding application release 2026b4cca52bd1e58d5f28a8e2cffe3f9e5b5204, ordinary live visual run 45841346962. Subsequent data-only changes preserved. Actual live baseline reviewed: crowded navigation and dataset-first landing page. Decision: make the landing page a discovery/workflow hub; organize existing deep links under five task groups; preserve grouped mobile selection; add 2–4 exact-source saved-record comparison including qualified capacity units and same-CCN/state nursing citation aggregates. No new raw data exposure.

## Next substantive priorities

1. Improve actual provider evidence profiles using individually cleared fields from the 1,433-field routing plan; validate each source pin, value domain and reuse scope first.
2. Add comparable historical regulatory timelines and domain evidence only where source row-level publication is approved; qualify entity/organization relationships before organization profiles.
3. Improve task-specific search and comparison, map-to-profile navigation, exports and evidence-based benchmarking without inferred risk/purchasing claims.
4. Build meaningful changes/alerts and persistent research accounts only after historical snapshots, entity grain, access and storage are qualified.
5. Resolve authorized permanent private recovery storage and full-size restore. GitHub Pages remains public/static. No raw or restricted database in public repository.

## Discovery handoff candidate — 2026-11-27 UTC

Baseline main `96b7fc1c1bb6db3a9a542c4f9c7f46e2d98e8c3d`; production application files unchanged since named nursing portfolio release `488b7da2eb6520983bec780fec3cc8cbea43780f` according to repository compare. Direct ordinary live URL and real connected-browser access unavailable in this session; this is not a live verification receipt. Candidate connects selected market category/jurisdiction and legacy quick search to the existing advanced facility research workspace, retaining exact query filters and all old links. No new source data or inferred relationships, no CSS edits, storage changes or TowerSignal changes. Candidate must pass asset stamps, existing actual-data browser tests, four viewport tests including handoff counts and back/forward, and personally inspected candidate screenshots before promotion. Then follow AGENTS.md for actual live verification. Next: assess newly reviewed nursing/hospital/dialysis fields for explicitly cleared per-record public use, then expand dossiers and comparisons; do not treat the field review as publication clearance.

### Visual review correction

Current main Pages deployment run 45916174831 succeeded at the baseline SHA; live visual run 45914086119 captured the preceding identical application assets. Its four-width screenshots were inspected. Initial candidate 06da515716448c0004cec8faa6c03df7f93d2666 passed repository verification 45919812928, institutional browser 45919812933 and handoff browser 45919812953 (artifact 15164171807). Actual visual inspection at all four widths identified inherited scroll position on market-to-advanced navigation (390/768/1024), cramped quick-search evidence labels (768), and early quick-search screenshot capture. Do not promote that candidate. Corrected candidate scopes scroll reset to discovery handoffs, protects quick-search table evidence/capacity labels, waits for completed source searches and asserts bounded table scrolling and destination scroll position. Requalification and new screenshot inspection required before promotion. No data, unrelated CSS, private storage or TowerSignal modifications.
