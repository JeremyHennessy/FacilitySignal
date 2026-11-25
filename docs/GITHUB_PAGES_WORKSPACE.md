# GitHub Pages public research workspace

Owner requested GitHub Pages instead of paid hosting (2026-11-25).
The existing Pages configuration deploys the root of main to https://jeremyhennessy.github.io/FacilitySignal/.
Static HTML/CSS/JavaScript is isolated from the Python/SQLite development application and the ongoing data custodian.

The browser reads only existing public aggregate source metadata and issues bounded queries directly to public official CMS APIs. No raw data, integrated database, restricted ownership projection, hospital narrative, secret, customer data or synthetic result is published. Historical qualification counts are not current loaded database counts. Queries depend on publisher availability, CORS, source schemas and rate limits. Source-specific rows are not canonical properties. Global search currently targets hospitals; other provider categories are selected in Facilities. Full integrated joins, secure accounts and restricted data cannot be implemented safely with Pages alone.

Candidate testing must verify navigation at 390/768/1024/1440px, filtered official API requests in an actual browser, empty/error handling, and the deployed URL. Do not claim full public data integration solely from a successful Pages workflow. Keep the original data and UI development branch unchanged.
