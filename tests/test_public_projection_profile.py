"""Exercise the actual committed public data and negative profile cases."""
import json
from pathlib import Path
import tempfile
import unittest
from scripts.profile_public_projection import build, profile_field, profile_shard

class PublicProjectionProfileTests(unittest.TestCase):
    def test_full_committed_public_projection(self):
        result = build()
        self.assertEqual(result["sources_profiled"], 9)
        self.assertEqual(result["provider_rows"], 48004)
        self.assertEqual(result["citation_source_rows"], 619069)
        # Aggregate-only log, one line per shard; no provider-level contents.
        for source in result["sources"]:
            print("PUBLIC_FIELD_PROFILE", json.dumps(source, sort_keys=True), flush=True)
        print("PUBLIC_FIELD_PROFILE_TOTAL", json.dumps({
            k: v for k, v in result.items() if k != "sources"
        }, sort_keys=True), flush=True)

    def test_missing_not_zero(self):
        got = profile_field([{"capacity": v} for v in ("", "  ", None, "0", "7", "-1", "n/a")],
                            "capacity", True)
        self.assertEqual((got["blank"], got["null"], got["zero_rows"], got["sum"]), (2, 1, 1, 7))
        self.assertEqual(got["non_numeric_or_negative"], 2)
        self.assertIsNone(profile_field([{"capacity": ""}], "capacity", True)["sum"])

    def test_wrong_grain_and_release_rejected(self):
        row = {"ccn": "000001", "state": "NY", "name": "Synthetic", "citation_rows": 3}
        expected = {"published_records": 1, "source_rows": 3}
        obj = {"source": "nursing-fire", "release": "2026-01-01", "row_count": 3, "records": [row]}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "data.json"
            path.write_text(json.dumps(obj))
            self.assertEqual(profile_shard(path, "nursing-fire", expected, "2026-01-01", {"NY"})["source_rows"], 3)
            with self.assertRaises(ValueError):
                profile_shard(path, "nursing-fire", expected, "2026-01-02", {"NY"})
            obj["records"][0]["citation_rows"] = 4
            path.write_text(json.dumps(obj))
            with self.assertRaises(ValueError):
                profile_shard(path, "nursing-fire", expected, "2026-01-01", {"NY"})
            obj["records"] = [row, row]
            path.write_text(json.dumps(obj))
            with self.assertRaises(ValueError):
                profile_shard(path, "nursing-fire", {"published_records": 2, "source_rows": 8},
                              "2026-01-01", {"NY"})

if __name__ == "__main__":
    unittest.main()
