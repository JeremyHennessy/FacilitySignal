import json
import unittest
from pathlib import Path
from scripts.qualify_asc_quality import HEADER

ROOT=Path(__file__).resolve().parents[1]

class ASCMeasurePeriodTests(unittest.TestCase):
    def test_documentation_reconciles_exact_header_and_pinned_release(self):
        evidence=json.loads((ROOT/"research/fs041_measure_period_review_20261127.json").read_text())
        audit=json.loads((ROOT/"research/fs041_asc_quality_qualification_20261127.json").read_text())["audit"]
        self.assertEqual(evidence["source_sha256"],audit["publisher"]["sha256"])
        self.assertEqual(evidence["source_release"],audit["publisher"]["released"])
        self.assertEqual(evidence["source_rows"],audit["input_rows"])
        fields=[x["field"] for x in evidence["identity_fields"]]+[f for m in evidence["measures"] for f in m["fields"]]
        self.assertEqual(len(fields),47)
        self.assertCountEqual(fields,HEADER)
        self.assertCountEqual(fields,audit["field_presence_profiles"].keys())
        self.assertEqual(len(evidence["measures"]),12)
        byid={m["measure_id"]:m for m in evidence["measures"]}
        claims={"ASC_12","ASC_17","ASC_18","ASC_19"}
        self.assertEqual({k for k,m in byid.items() if m["source_method"]=="Medicare claims"},claims)
        self.assertEqual(byid["ASC_12"]["collection_start"],"2022-01-01")
        self.assertTrue(all(m["collection_end"]==("2024-12-31" if k in claims else "2025-12-31") for k,m in byid.items()))
        self.assertTrue(all(m["collection_start"]==("2022-01-01" if k=="ASC_12" else "2023-01-01" if k in claims else "2025-01-01") for k,m in byid.items()))
        self.assertTrue(all(m["clinical_value_qualified"] is False for m in byid.values()))
        self.assertEqual(evidence["counts"]["app_qualified_fields"],0)
        self.assertEqual(evidence["counts"]["raw_value_domain_qualified_fields"],0)
