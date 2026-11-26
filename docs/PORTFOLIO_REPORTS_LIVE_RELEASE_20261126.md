# Portfolio reporting live release — November 26, 2026

Release completed for commit 1139b157bd4c94bd208df1707a3eaed4a6326dc9. Previous deployed baseline 61ec8bcf4341b3bf84abdd33f7d4afe77e5cb76a, Pages 45868800996. Expected-SHA fast-forward; no concurrent main changes overwritten. PR #50 merged.

- Candidate automated verification 45871710619 passed; architecture/browser regression 45871703255 passed, including download content/filter checks and actual overflow/action checks. Candidate artifact 15142553791 visually reviewed: all four widths, portfolio and comparison, 390/768 scrolled portfolio actions, overview and navigation. 1024 prior clipping eliminated with wrapped headers; smaller widths scroll intentionally.
- Pages build/deploy run 45872090844 passed. Main verification 45872091020 passed.
- Ordinary live URL and UTM variant verification 45872090874 passed; warm-cache map render verified. Actual loaded SHA-256: index a6788828a7b0252ddc266c1521edbc8b609f0b094dfc8f77b00867bb454b34a1; JS 33495b2b927db4bce84d1c5150301f2f309dbb4c29cb84ef2de12c512b4286f6; CSS e33f0c2631ab272d9a78b3e691811885bca192a7984ea5a8d05633824c8f1e2f. Normal URL took four attempts during propagation; UTM variant one attempt. No universal cache-freshness claim.
- Live artifact 15143765220, report.json 120 screen records; actual images inspected for populated portfolio/export controls, comparison export controls, national overview, and market map at 390, 768, 1024, 1440; scrolled portfolio at 390 and 768. Remove buttons intact at 1024 and after scroll. Live screenshots agree with candidate layout in affected regions. Existing responsive navigation and maps preserved. Other routes covered by automated live/browser checks, not all 120 screenshots individually inspected.
- Production public URL: https://jeremyhennessy.github.io/FacilitySignal/#saved-portfolio. No data packs, private Blob objects or source mappings changed by release. TowerSignal unchanged by this slice.

Research branch retains this custody note to avoid another unrelated production rebuild. No individual financial or historical capacity row publication in this release.
