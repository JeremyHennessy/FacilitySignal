# PECOS organization and enrollment semantic qualification — 2026-11-26

## Scope and evidence

- [All six pinned releases](../research/pecos_role_semantic_audit_20261126.json): qualification run [45828076053](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45828076053), exact executed commit d2580319c47ccad8f7c3280c74ebd37c47b76c44, four targeted tests and source pass.
- [All 186 original source columns](../research/pecos_field_semantic_crosswalk_20261126.json): manually reviewed publisher definitions, application uses, original field order and per-field value qualification limits; not blanket permission to expose rows. July 2026 publisher dictionaries for all six files are linked in the audit. The [hospital owner code table](https://data.cms.gov/sites/default/files/2026-07/Hospital_All_Owners_Data_Dictionary.pdf) and [SNF owner table](https://data.cms.gov/sites/default/files/2026-07/SNF_All_Owners_Data_Dictionary.pdf) have 14 and 19 codes respectively. See [SNF data guidance](https://data.cms.gov/sites/default/files/2026-07/SNF_Data_Guidance.pdf), sections 3.4–3.6 and Appendix H.
- [Targeted follow-up](../research/pecos_semantic_followup_20261126.json): run [45828422101](https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45828422101) passed on three small pinned files only, resolving label wording and inspecting enrollment subgroup flags. No full national reconstruction, raw source retention, paid storage or personal data publication.

All six source hashes matched the release lock. Input 479,387 rows, 152,606 retained; 326,781 individual-owner rows skipped before other field access. Organizational role rows are self-reported; group codes, PAC IDs and enrollment IDs are not legal property titles. No row-level ownership, flags, facility associations or buyer/seller records are published by this audit.

## Role classification

| Role class | Hospital rows | SNF rows |
|---|---:|---:|
| Direct ownership (34, 85 where applicable) | 6,305 | 14,224 |
| Indirect ownership (35, 86 where applicable) | 10,500 | 25,318 |
| Operational/managerial control (43) | 4,342 | 12,696 |
| Financial interest (36/37) | 385 | 3,224 |
| Partnership (38/39) | 516 | 753 |
| Additional disclosable party (72) | Not in hospital dictionary | 43,100 |
| Trustee (71) | Not in hospital dictionary | 515 |
| Other (44) | 687 | 401 |

All 122,966 role descriptions agree with the applicable role code, and all rows have a valid organization PAC and exact same-family enrollment/PAC candidate. Role grouping is an explicitly documented analytical choice. No role rows in additional permitted codes were observed. The role code and text should remain separate source fields; unknown/conflicting future values must be quarantined. The 559 observed below-five-percent numeric values on threshold-labeled ownership/mortgage/security roles (164 hospital and 395 SNF) are review flags, not grounds for rejecting the role or concluding legal noncompliance.

Hospital: 4,083 distinct organization PACs; 2,203 with multiple matched enrollments. SNF: 30,518 distinct organization PACs; 5,115 with multiple matched enrollments. 802 exact tokens occur in both source families; 33,799 in their literal union. These are source entity identifiers; no deduced cross-family property ownership. Distinct enrollment-role keys reconcile to 122,966. Organization-enrollment-provider candidate pairs are 20,755 hospital and 78,333 SNF; multiple roles can belong to a single pair.

## Type flags and entity aggregation

All 17 hospital and 19 SNF organization flags have aggregate counts and organization-level yes/no conflict counts. Selected examples:

| Flag | Hospital PACs with reported yes | Hospital PACs with both yes/no | SNF PACs with reported yes | SNF PACs with both yes/no |
|---|---:|---:|---:|---:|
| Management services company | 107 | 55 | 1,453 | 331 |
| Medical staffing company | 5 | 5 | 848 | 64 |
| Consulting firm | 5 | 3 | 2,345 | 265 |
| Private equity | 23 | 20 | 108 | 25 |
| REIT | 3 | 0 | 417 | 40 |
| Chain home office | 215 | 189 | 340 | 180 |

SNF parent company: 1,010 PACs with at least one affirmative record, 277 with both affirmative and negative records; 68,354 role rows have blank flag. Blank does not mean independent or not parent. A "yes" row and a "no" row can coexist for one source entity; do not flatten to a definitive classification. Flags describe reported organization characteristics, not a verified named vendor contract. The audit deliberately does not sum ownership percentages across entities, roles or incomplete institutional-only records.

## Enrollment and CHOW context

- 9,120 hospital and 14,401 SNF enrollments have valid unique enrollment/PAC pairs. Provider PAC cardinalities 5,269 and 12,230; 2,619 and 343 PACs have multiple enrollments. NPI repeated across different enrollment/PAC pairs: 421 hospital and three SNF. The CCN six-character candidate check excluded 75 and 169 nonstandard-for-that-join tokens, not necessarily invalid CMS IDs (dictionary field permits up to 15 characters). Preserve original tokens.
- Among 6,119 CHOW rows, code AM appears 116 hospital and two SNF; CH appears 663 hospital and 5,338 SNF. No CO. The first audit recorded all 6,001 CH text labels as differing from the July dictionary's parenthetical wording. Targeted follow-up confirmed every row uses either that July label or the exact January hospital dictionary variant "Change of Ownership". Both July dictionaries assign CH the same meaning. No unknown CHOW code/text remains in these pinned sources. The earlier SNF-specific January dictionary was not retrieved, so the exact historical reference is the hospital code table and matching July SNF code definition. The original mismatch remains recorded in the initial audit; follow-up supersedes its interpretation, not its observations.
- Historical CHOW buyer enrollment/PAC matches the November source for 765 hospital and 5,305 SNF rows. Sellers match in only one and three rows respectively. Historical seller absence is expected in a later current enrollment snapshot; not an ingestion loss. CHOW records are not unique property deeds. 4,376 effective dates have ambiguous slash order under the conservative parser; do not coerce date order without evidence. Similarly 63,293 owner association dates remain ambiguous, and ten SNF association dates parse later than the audit date. No current control inferred.
- Hospital enrollment has all 13 subgroup flags in exact Y/N domain; 2,792 records with no affirmative subgroup; 1,844 records with multiple affirmative subgroups. The flags are not mutually exclusive. Acute care 3,006; general 1,517; psychiatric 814; psychiatric unit 912; rehabilitation 670; rehabilitation unit 840; swing-bed approved 402. These are enrollment classifications, not distinct facilities, equipment or capacity measures.
- REH conversion: 57 affirmative enrollment flags, 51 with a prior hospital/CAH CCN reference, six without. Conversion dates: 19 ambiguous and 32 parsed, 9,069 blank. Treat as program transition evidence, not evidence of current site closure or building identity.

## Application design and remaining limits

Use separate reported role classes, source-family PAC/enrollment links, conflict-aware flag distributions and independently reviewed source labels. Public workspace may expose selected aggregate-only tables; local query use should preserve the role record, as-of period, exact join evidence and ambiguity. Before individual portfolio views are expanded, verify lawful reuse, identity corroboration, and source-scoped ownership/management rather than infer an ultimate parent. Current value-domain review remains open for several enrollment specialty/organization type codes and date formats. No new production ingestion or canonical property merges are authorized by this research.
