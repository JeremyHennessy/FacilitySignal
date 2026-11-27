# FS-040 state context is not a provider benchmark label

From the [CMS state catalog](https://data.cms.gov/provider-data/dataset/k2ze-bqvw) indexed official display, these checks processed the first complete single-jurisdiction screen, 18 rows: six measure-family SIR points with lower and upper interval endpoints. All six triplets were numeric and ordered within the exact November 12, 2026 edition and CY 2025 window. This is a test of coverage, integrity and distinct reporting grain, not a result about how a jurisdiction or hospital performed. The trailing incomplete second jurisdiction was not processed.

The four SIRs from the preceding [hospital screen](https://data.cms.gov/provider-data/dataset/77hc-ibv8) were explicitly rejected as different-jurisdiction settings for the state context. Even same-jurisdiction matches would provide only aggregate context; the existing publisher Compared to National field is not regenerated under a state benchmark, and interval shape does not change a publisher label. No provider or jurisdiction labels, values, rows, causal or campus claims appear in the retained receipt.

A narrow official datastore read using one exact facility filter and limit 1 was attempted through the text browsing route; the tool reported the URL inaccessible and returned no JSON or HTTP publisher status. The 1,008 state and 172,332 hospital totals are displayed catalog metadata only, not independently counted full payloads. The checksum covers a transient minimal display projection, not raw API/CSV bytes. No corpus ingested, network retries, storage writes, searches for records behind new permissions, or public app changes.

Run the focused HAI tests with `python -m unittest discover -s tests -p 'test_*hai*.py'`.
