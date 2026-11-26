# FacilitySignal release instructions

## Mandatory live visual release gate (owner instruction, 2026-11-26)

A successful deployment, HTTP status, candidate test, asset-hash check or DOM assertion is NOT a completed public release. Do not report an update as complete until the ordinary public GitHub Pages URL actually renders the intended change in a real browser and a responsible agent has inspected the live screenshots.

1. Preserve the current deployed SHA and approved UI before changing files; use isolated branches, minimal scoped changes, and expected-SHA promotion. Keep TowerSignal unchanged.
2. If web/pages.js or web/pages.css changes, run `python scripts/stamp_pages_assets.py --write` and include the resulting index.html in the exact qualified candidate. `--check` is mandatory in CI. Versioned asset URLs reduce stale script/style mixtures; they do not guarantee a stale cached HTML entry point has expired.
3. Qualify the candidate at 390, 768, 1024 and 1440 pixels. Review actual screenshots of changed screens and check unaffected approved layouts.
4. After deployment, run the live visual release workflow against the **ordinary public URL**, including the common ChatGPT UTM link and a warm-cache reload. Verify the actual browser-loaded asset hashes and intended functionality, not merely a cache-busting test URL.
5. Inspect the real live screenshots at all four widths, including the changed feature in view, and compare with candidate/baseline. A screenshot artifact existing is not proof of a visual review. Capture safe evidence for relevant public routes; never screenshot restricted payloads.
6. Record the deployed SHA, ordinary URL, run ID, actual asset verification, screenshots inspected, checks, defects and outstanding limitations. If screenshots cannot be viewed, deployment or visual checks fail, or the user's actual browser still shows an older release, report the blocker; do not claim release complete.
7. Check that links and browser back/forward, filters, empty/error states, responsive readability and user-facing behavior remain correct. A build-only success is insufficient. For delivery issues investigate the user's actual view when available; do not redesign functioning screens.

The project remains a static public research app on GitHub Pages, distinct from local Python/SQLite research. No restricted publication, new paid infrastructure or storage transfer without authorization. Coordinate with the existing FacilitySignal Data Custodian. All historical data qualification, source provenance and approved visual baselines remain protected.
