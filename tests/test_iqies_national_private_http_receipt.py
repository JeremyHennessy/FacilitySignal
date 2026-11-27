"""Reconcile retained national HTTP evidence to the original qualified service and recovery receipts."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "research"


def receipt(name):
    return json.loads((ROOT / name).read_text())["receipt"]


class NationalPrivateHTTPReceiptTests(unittest.TestCase):
    def test_qualified_release_and_recovery_parity(self):
        http = receipt("iqies_national_private_http_20261127.json")
        service = receipt("iqies_national_service_qualification_20261127.json")
        recovery = receipt("iqies_sidecar_roundtrip_20261127.json")
        self.assertEqual(http["database_sha256"], service["database_sha256"])
        self.assertEqual(http["database_sha256"], recovery["restored_database_sha256"])
        self.assertEqual(http["base_release"], service["base_release"])
        self.assertEqual(http["base_release"], recovery["base_release"])
        self.assertEqual(http["source_records"], service["baseline_source_records"])
        self.assertEqual(http["service_observations"], service["observations"])
        self.assertEqual(http["service_observations"], recovery["observations"])
        self.assertEqual(sum(sum(x.values()) for x in service["field_states"].values()),
                         http["service_observations"])
        self.assertEqual(http["service_fields"], len(service["field_states"]))
        self.assertEqual(service["field_states"], recovery["field_states"])
        self.assertEqual(http["checks"]["field_state"],
                         sum(len(x) for x in service["field_states"].values()))

    def test_complete_http_checks_and_publication_boundary(self):
        http = receipt("iqies_national_private_http_20261127.json")
        fields = http["service_fields"]
        counts = http["checks"]
        for key in ("all_states", "pagination", "geography"):
            self.assertEqual(counts[key], fields)
        self.assertEqual(counts["literal_search"], fields + 3)
        self.assertEqual(counts["invalid_requests"], 7)
        self.assertEqual(counts["default_denial"], 1)
        self.assertEqual(http["successful_requests"],
                         sum(v for k,v in counts.items()
                             if k not in ("invalid_requests","default_denial")))
        self.assertTrue(http["database_unchanged"])
        self.assertTrue(http["national_pointer_unchanged"])
        self.assertTrue(http["loopback_only"])
        self.assertFalse(http["private_storage_written"])
        self.assertFalse(http["public_promotion"])
        self.assertEqual(http["response_rows_published"], 0)
        self.assertGreater(http["max_successful_request_ms"], 0)
