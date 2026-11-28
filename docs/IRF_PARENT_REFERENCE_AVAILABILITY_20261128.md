# FS-043 — IRF parent reference availability, 2026-11-28

Reviewed exact existing aggregate profiles and dictionary crosswalks, not raw source rows. No new downloads, Azure access or property linkage.

| Field | Pinned scope | Blank | Other states | Interpretation boundary |
|---|---:|---:|---:|---|
| QIES PARENT_PROVIDER_NUMBER | 13,598 | 13,598 | 0 | Historical layout occurrences are category 12 and 14; not evidence of a hospital IRF parent. |
| QIES CAH_REHAB_DPU_SW | 13,598 | 11 | 13,587 | Historical CAH-specific indicator; current domain and applicability require review. |
| QIES TOT_OFSITE_REHAB_UNIT_CNT | 13,598 | 11 | 13,587 | Count, not parent identifier. |
| QIES REHAB_UNIT_BED_CNT | 13,598 | 9 | 13,589 | Historical PPS-exempt rehabilitation bed count, not property count. |
| QIES REHAB_UNIT_EFCTV_DT | 13,598 | 11,946 | 1,652 | Historical exemption date, not opening date. |
| QIES REHAB_UNIT_SW | 13,598 | 9 | 13,589 | Historical hospital PPS-exempt rehabilitation unit indicator. |
| QIES REHAB_UNIT_TRMNTN_CD | 13,598 | 11,946 | 1,652 | Historical exemption termination reason, not closure. |
| QIES REHAB_UNIT_TRMNTN_DT | 13,598 | 12,904 | 694 | Historical exemption termination date, not closure. |
| PECOS CAH OR HOSPITAL CCN | 9,120 | 9,069 | 51 | REH conversion predecessor reference; not a rehabilitation parent relationship. |

The pinned Q3 2026 QIES raw aggregate profile contains no populated direct parent-number values. The November PECOS hospital enrollment reference is defined in its reviewed dictionary as a conversion predecessor reference. Neither field can directly qualify any of the 810 IRF parent candidates. Populated counts are not affirmative counts; no yes/no inference is made. The six other QIES hospital rehabilitation observations and CAH indicator can provide independent contextual corroboration if an authorized pinned row-level source is available, but cannot establish a campus, legal operator, or exact unit-parent relationship by themselves.

The reproducible aggregate audit verifies the four exact committed evidence blobs, source checksums, grain, field ordinals and reconciled counts. See scripts/audit_irf_parent_field_availability.py. For future row-level work, retain literal exact CCNs, category scope, dates, and conflicting or absent observations; require independent authoritative relationship evidence before any link promotion. No new application clearance.
