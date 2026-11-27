"""Cross-family gate for the 19 original pinned releases, not expanded Azure inventory.

The November 26 index is deliberately immutable historical evidence. Later overlays
complete field-by-field review without replacing original raw profiles or approving
new publication. This test binds the overlays by exact Git blob and field ordinal.
A historical candidate, provisional definition, or populated cell is not a qualified
domain or a production projection. No downloads or live Azure access.
"""
import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = "research/national_data_understanding_index_20261126.json"
INDEX_BLOB = "2d4b60ea413e60c96a9500a4d5713b6d90bca03a"
# Source family keys, evidence basename and exact reviewed blob.
OVERLAYS = (
    (("hospital",), "hospital_column_semantics_20261126.json", "3fb8cea6d23bcb545d422c3a165cbb89a8a533aa"),
    (("nursing",), "nursing_column_semantics_20261127.json", "8ce0b647030375bd8918dcf55ce9ef5dbc2a9fc1"),
    (("dialysis",), "dialysis_column_semantics_20261126.json", "7f82c25a9975019f9205220a650664e9e064399a"),
    (("nursing-fire", "nursing-health"), "care_compare_citation_column_semantics_20261127.json", "d0aa7edebf2c026b6e525a56a7e83eb6bc66cec4"),
    (("home-health",), "hha_column_semantics_20261126.json", "90aac8a80bf387fc9f0d8ff9c823206daa0340e9"),
    (("hospice", "long-term-hospital", "rehabilitation"), "postacute_directory_semantics_20261126.json", "86d7dd600ed2ae2199169754a4285ea82d8f5263"),
    (("qies",), "qies_historical_dictionary_crosswalk_20261126.json", "d3ba3da2c42af3ead3cf573ebd3016b8972a7d84"),
    (("iqies",), "iqies_semantic_application_crosswalk_20261126.json", "52c58708bd65156fbac5d2f2c98fabeb72010b07"),
    (("clia",), "clia_historical_dictionary_crosswalk_20261126.json", "c06a3ffad8236f00eecc66f4e72e05399a71bde7"),
    (("qcor-hospital",), "qcor_hospital_column_semantics_20261127.json", "6a4a461347008b647ea9181adf65c88f4df12e81"),
    (("hospital-enrollment", "hospital-owner", "hospital-chow", "snf-enrollment", "snf-owner", "snf-chow"), "pecos_field_semantic_crosswalk_20261126.json", "dbe7a6354926cd27e67145d3d596164ef03708a0"),
)


def read_pinned(path, expected):
    raw = (ROOT / path).read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if actual != expected:
        raise AssertionError(f"Reviewed evidence changed: {path}: {actual} != {expected}")
    return json.loads(raw)


def field_keys(source):
    return [(f["ordinal"], f["field"]) for f in source["fields"]]


def baseline_partition(field):
    # Mutually exclusive: preserve blank before restricted classification.
    # 'Projection' means recorded baseline mapping, not current runtime usage.
    if field["existing_projection_20261126_baseline"] is not None:
        return "baseline_mapped"
    if field["all_blank"]:
        return "unmapped_all_blank"
    if field["profile"] == "contact_or_personal_presence_only":
        return "unmapped_presence_only"
    # Other presence-only profiles (e.g. QCOR narratives) also lack distinct counts.
    if field["distinct"] is None:
        return "unmapped_presence_only"
    if not field["other_nonmissing_or_present"]:
        return "unmapped_no_nonmissing"
    return "unmapped_populated_aggregate"


class AllSourceSemanticCoverageTests(unittest.TestCase):
    def setUp(self):
        self.index = read_pinned(INDEX, INDEX_BLOB)
        self.sources = {s["source"]: s for s in self.index["sources"]}

    def test_every_original_field_has_exact_semantic_review_evidence(self):
        seen = set()
        field_count = 0
        for source_keys, basename, blob in OVERLAYS:
            overlay = read_pinned("research/" + basename, blob)
            entries = {s["source"]: s for s in overlay["sources"]} if "sources" in overlay else {source_keys[0]: overlay}
            self.assertEqual(set(entries), set(source_keys))
            for key in source_keys:
                with self.subTest(source=key):
                    self.assertNotIn(key, seen)
                    seen.add(key)
                    source, reviewed = self.sources[key], entries[key]
                    self.assertEqual(field_keys(reviewed), field_keys(source))
                    if "source_sha256" in reviewed:
                        self.assertEqual(reviewed["source_sha256"], source["sha256"])
                    if "rows" in reviewed:
                        self.assertEqual(reviewed["rows"], source["profiled_rows"])
                    field_count += len(reviewed["fields"])
        self.assertEqual(seen, set(self.sources))
        self.assertEqual((len(seen), field_count), (19, 1433))

    def test_baseline_mapping_gap_partition_is_exhaustive(self):
        totals = Counter(baseline_partition(f) for s in self.sources.values() for f in s["fields"])
        self.assertEqual(totals, {
            "baseline_mapped": 248,
            "unmapped_all_blank": 299,
            "unmapped_presence_only": 23,
            "unmapped_populated_aggregate": 863,
        })
        self.assertEqual(sum(totals.values()), self.index["totals"]["columns"])
        # The 31 restricted profiles include eight entirely blank occurrences.
        # A baseline mapping does not authorize exposure of any literal value.
        self.assertEqual(sum(f["distinct"] is None for s in self.sources.values() for f in s["fields"]), 31)
        self.assertEqual(sum(f["distinct"] is None and baseline_partition(f) == "baseline_mapped"
                             for s in self.sources.values() for f in s["fields"]), 0)
        self.assertEqual(sum(f["distinct"] is None and f["all_blank"]
                             for s in self.sources.values() for f in s["fields"]), 8)
        for key, expected in (("qies", 162), ("iqies", 164), ("clia", 89)):
            self.assertEqual(sum(baseline_partition(f) == "unmapped_populated_aggregate"
                                 for f in self.sources[key]["fields"]), expected)

    def test_registry_qualification_limits_not_erased(self):
        for key in ("qies", "clia"):
            self.assertTrue(all(f["semantic_status"] == "historical_2023_publisher_candidate_only"
                                for f in self.sources[key]["fields"]))
        self.assertEqual(sum(f["semantic_status"].startswith("blocked")
                             for f in self.sources["iqies"]["fields"]), 5)
        self.assertTrue(all(f["application_approval"] == "not_granted_by_this_audit"
                            for s in self.sources.values() for f in s["fields"]))


if __name__ == "__main__":
    unittest.main()
