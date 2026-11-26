# Nursing-home chain affiliation and inspection semantics — November 26, 2026

## Evidence and scope

Qualification [45826186143](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45826186143), exact source-analysis commit `12603334f1a83ca0c1e9ac5842dedd04797a6803`: both jobs succeeded. [Machine-readable aggregate audit](../research/nursing_semantic_audit_20261126.json) records each original source SHA-256, release, counts and actual value-domain reconciliation. No raw individual rows, names, addresses, CCNs or affiliation IDs are retained in this audit. No live-site or legal-title claim. The 19-release national source baseline remains unchanged.

Reviewed CMS [nursing-home consolidated dictionary](https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/nursing_home/NH_Data_Dictionary.pdf), Tables 2, 6 and 7, including rendered pages. Extracted text identifies October 2026; rendered page footers identify June 2026. Record this revision mismatch; rely only on the documented fields and actual pinned values, not a claim that every October definition is fully current. Also reviewed July 2026 [SNF enrollment dictionary](https://data.cms.gov/sites/default/files/2026-07/SNF_Enrollments_Data_Dictionary.pdf) and [data guidance v1.8](https://data.cms.gov/sites/default/files/2026-07/SNF_Data_Guidance.pdf), especially affiliation methodology and limitations.

## Field meanings and appropriate use

| Field | Interpretation and use |
|---|---|
| Chain ID / Chain Name | CMS's reported group identifier/name for nursing homes linked through ownership, officer or managerial relationships; keep source/release scope. Do not use as a corporate legal entity or property-owner ID. |
| Number of Facilities in Chain | Group membership count repeated per member. Compare to count of members; never sum repeated values. |
| PECOS AFFILIATION ENTITY ID / NAME | Publisher grouping of SNFs based on its network-analysis methodology. Keep separate from chain IDs, PAC IDs, enrollment IDs and CCNs. Compare via exact CCN and corroborating reported state first; equal group tokens do not prove release-independent identity. |
| Standard / Complaint / Infection Control Inspection Deficiency | Independent Y/N source flags for how a cited deficiency was identified. More than one can apply. Not an exhaustive inspection count or current safety finding. |
| Citation under IDR / IIDR | Source-reported informal / independent informal dispute-resolution indicators at the snapshot. These flags do not establish disposition, legal outcome, present-day compliance, or confirmed unresolved violations. |
| Inspection Cycle | Source cycle number 1/2/3, with source-specific standard/complaint time rules. Do not interpret as elapsed years. |
| Fire Tag Version | Old/new version boundary July 5, 2016; keep version and tag prefix together. The health citation CSV has no corresponding tag-version field. |

## Actual source reconciliation

- Nursing provider file October 28: 14,686 rows; 10,227 valid chain IDs, 4,459 blank; no malformed IDs or name/size presence conflict. All 612 groups have one reported normalized name, consistent reported size and exact observed membership count. Nine groups have 100+ records; 118 have 20–99; 419 have 5–19; 66 have 2–4.
- SNF enrollment November: 14,401 records; 10,162 populated valid affiliation IDs and 4,239 blank; 613 distinct tokens. 14,209 exact nursing CCN candidate rows, including 14,207 with matching reported state, one conflict and one missing state. 192 have no exact nursing CCN candidate.
- Within same-CCN/state pairs, 9,981 equal nonblank group tokens, including 9,976 equal normalized name texts and five differing texts; 21 different nonblank tokens with different names; 155 one missing group; 4,050 both missing. There are 611 shared literal group tokens across namespaces. Never silently merge the 21 ID conflicts, five name discrepancies or missing groups. The release periods differ, so changes may reflect timing or methodology rather than errors.
- Nursing health citations: 418,682 rows; 631 IDR, 131 IIDR, none with both. 317,950 standard, 129,397 complaint, 708 infection-control; 28,725 standard+complaint and 648 complaint+infection-control. Fire citations: 200,387 rows; 69 IDR, one IIDR, none with both; 198,884 standard, 1,579 complaint, no infection-control, 76 standard+complaint. Across both sources there are 832 rows with at least one reported dispute flag. These are historical rows, not unique dispute cases or current unresolved citations.
- All 200,387 fire rows carry the new tag version and agree with the documented survey date boundary. Every inspection cycle token in both sources is 1, 2 or 3. All five flags reconcile to exact Y/N with no unknowns in the pinned releases.

## Application gates

Use the existing national compliance and data/ownership research surfaces for approved aggregates only. For future local source-scoped portfolio functions, carry release, source key and evidence class; do not infer a legal owner from group name/ID or use incomplete group coverage as independence. Retain disputed flag context separately from severity, correction status and chronology. Explicitly distinguish historical tag dictionary version, survey type and actual correction semantics. Additional row-level publication requires reuse review; no raw records or new provider-level relationships are authorized by this audit.
