# Historical capacity candidate visual review — 2026-11-26

Candidate run 45872925776 at 81ee847d7169c53a426dc6e75e64f24ca03bfd11 passed exact data regeneration and verification, all unit checks, dedicated historical capacity Chromium qualification at 390/768/1024/1440, facility profile/dossier/portfolio architecture regressions, and isolated retention of the two generated public PUF files.

Candidate artifact 15144665197 contains 32 screenshots. Reviewed representative hospital-qualified, hospital-missing, nursing-multiple-period and nursing-unlinked screenshots across all four viewport widths (16 images). No clipping or overlap was observed in those reviewed screenshots. Distinct periods, missing values and unmatched evidence remain explicit. Existing source capacity and historical capacity are separate. Other cases passed automated checks; not every screenshot individually inspected.

Bot retention commit 7f75f6e51e0e6dfb59b65cc3a75fb1d8c2625de8 adds only web/hcris-capacity/hospital.json (546382 bytes) and snf.json (2434448 bytes). PR-triggered verification 45873235228 returned action_required with no jobs; not counted as a pass. Now that both packs exist, switch the dedicated workflow to read-only committed-file validation with no automated commit or push. This triggers explicit qualification of the final committed candidate. Preserve original qualification and provenance. No changes to application or data bytes in this checkpoint. Main remains unchanged pending final qualification and ordinary live visual verification.

Previously deployed main: 1139b157bd4c94bd208df1707a3eaed4a6326dc9. No Azure access or monetary field publication.
