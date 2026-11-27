# National Rural Emergency Hospital OP-36 display

The official [national](https://data.cms.gov/provider-data/dataset/uk3n-au7a) and [hospital](https://data.cms.gov/provider-data/dataset/zez1-ka2w) November 12, 2026 release displays a CY 2024 measure window in the Rural Emergency Hospital Quality Reporting program. This is the outpatient surgery return-visit ratio, not the general hospital readmission program, a count of emergency calls, or a statement about service availability. See the [REH measure methods](https://qualitynet.cms.gov/reh/measures/surgery/methodology).

The complete national one-row display and first page of 25 provider rows were read and checked. The national rate is not available, even though CMS displays category counts (zero worse, two same, zero better, four too few). Those category counts are not the 49 provider rows shown in the publisher catalog metadata and are not a denominator from which to recreate the national rate. In the 25-row provider preview, exactly one score had numeric estimates; two displayed too few, 21 were unavailable for nonspecific reasons, and one had no eligible cases. The [official footnotes](https://data.cms.gov/provider-data/topics/hospitals/about-data) distinguish these cases. Unknown is not zero, and no eligible cases is not proof of zero events in an otherwise eligible group.

The detached checksum is for the transient minimized displayed projection, not a publisher CSV/API response. Only aggregate counts were retained. No provider identities, locations, evaluation of present performance, auto joins, app changes, or Azure writes. The remaining 24 provider rows and raw source bytes were not validated.

Run: `python -m unittest discover -s tests -p test_qualify_cms_reh_op36.py`.
