# Illinois hospital capacity: publisher aggregate cross-check (FS-151)

Date: 2026-11-27. Scope: publisher-document semantics and an aggregate arithmetic check; no new private archive, facility-level ingestion, linkage, or Pages release. Original source register untouched.

The [Illinois HFSRB inventories page](https://hfsrb.illinois.gov/inventories-data.html) separates CON-authorized bed tracking, individual profiles, health-service-area summaries, statewide summaries, and data explorers; it also lists other facility types separately. Do not treat these as interchangeable tables or as comprehensive live data. The publisher's [2024 statewide hospital profile](https://hfsrb.illinois.gov/content/dam/soi/en/web/hfsrb/documents/inventories-data/facility-profiles/hospital-facility-profiles-%28new%29/2024-Hospital-Profiles-Statewide.pdf) states 211 participating hospitals, CY 2024. The [CY 2025 questionnaire](https://hfsrb.illinois.gov/content/dam/soi/en/web/hfsrb/documents/inventories-data/facility-profiles/2025-facility-survey-forms/Hospital-Survey-2025-Short.pdf) defines observation days, peak staffed beds, and peak daily census separately. This is guidance for a different year, not evidence that all 2024 definitions were identical.

## First-page aggregate fixture

The table below is limited to statewide aggregates from three service lines (Total AMI is the source's aggregate label, not an equipment category).

| Service | CON authorized | Peak staffed | Inpatient days | Observation days | Published average daily census | CON occupancy | Staffed occupancy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Medical/surgical | 20,306 | 16,978 | 3,916,631 | 566,568 | 12,283 | 60.5% | 72.3% |
| Intensive care | 3,602 | 3,159 | 777,613 | 12,179 | 2,164 | 60.1% | 68.5% |
| Total AMI | 3,996 | 3,428 | 1,273,483 | 553 | 3,491 | 87.4% | 101.8% |

All nine published census/occupancy cells reproduce at their displayed precision if average daily census is (inpatient days + observation days)/365 and the occupancy numerators use that census before rounding, with their own denominators. Dividing by 366 instead fails all three rounded census checks; 2024 was a leap year. This is a three-row arithmetic inference, not an authoritative statewide calculation policy or justification to recompute values silently. The reported 101.8% is preserved as a source value with a review flag, not capped or interpreted as present occupancy. A source dash and a literal zero must be stored separately. The summary contains parent totals and breakdowns, so summing all rows would double count. This fixture checks 12 assertions: three each for census, authorized occupancy, staffed occupancy, and rejection of the naive leap-year substitution.

## Integration gates

- Store observation year, geography level, service label and parent/breakdown status, unit, authority (authorized versus staffed), and original null token, with source URL and page. Keep source-stated and inferred metrics separate.
- Keep this history separate from current hospital availability, equipment inventories, policy compliance, and hospital demand signals. For future provider-level study, use institutional license ID as a source-scoped key, review hospital/campus identity separately, and exclude personal contact, tax identifiers, and internal layouts. No name-only join.
- Next ingestion step: locate and checksum a bounded, machine-readable official hospital release; confirm row grain and reuse before archiving or exposing data. Require independent source row counts, reviewed column definitions, and an explicit publication gate. The statewide PDF fixture does not certify that release or advance any live feed.
