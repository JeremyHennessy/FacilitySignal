# Private nursing regulatory-history qualification

Scope: exact archived national and extension SQLite files; five source-specific historical evidence grains: 418,682 health citation rows, 200,387 fire citation rows, 148,956 survey-date rows, 43,931 survey-summary rows and 15,007 penalty rows. Total 826,963 source records, not unique inspections, providers, penalties or events. Existing pinned October 28, 2026 releases only. No new Azure writes or publisher retrieval.

The read-only local query requires exact nursing source CCN and directory state. Citation and penalty records must agree with their own stored state. Survey-date observations contain no source state; they are CCN-only directory candidates. Survey-summary projections retain the prior same-state test but not raw state; present that limitation explicitly. Never merge equal dates or repeated survey keys. Health and fire summary dates are independent, and date filters require an explicit choice. Preserve missing counts and explicit zero, source-reported plans and dates of correction, and historical reported fine/denial values. Do not infer current compliance, outstanding liabilities, procurement intent, or a risk score. No tag, narrative, facility name or address is exported by this query.

CI restores exact data from the existing authorized archive and emits aggregate-only evidence. Independently scan five source tables, compare prior lineage and links, compare sampled exact-provider search totals and pagination to the independent scan, and verify source bytes and storage pointers remain unchanged. No named provider results or row-level artifact are published. Actual archive qualification requires successful main workflow.

Authorized local use (replace paths and example identifier with exact private restored files and known nursing record):

`python -m scripts.nursing_regulatory_history profile --national /private/facilitysignal.sqlite3 --extension /private/extension.sqlite3 --ccn 000001 --state NY`

`python -m scripts.nursing_regulatory_history search --national /private/facilitysignal.sqlite3 --extension /private/extension.sqlite3 --source survey_summary --ccn 000001 --state NY --summary-date health --start 2024-01-01`

No public app changes in this increment. Individual inspection, penalty or oversight evidence remains local authorized access pending source-specific publication and UI qualification.
