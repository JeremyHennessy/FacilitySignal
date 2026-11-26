import json,unittest
from pathlib import Path
from scripts.build_market_summary import build
ROOT=Path(__file__).resolve().parents[1]
class MarketSummaryTests(unittest.TestCase):
    def test_exact_precomputed_aggregation(self):
        d=build(ROOT)
        self.assertEqual(d,json.loads((ROOT/"web/market-summary.json").read_text()))
        self.assertEqual(sum(sum(x.values()) for x in d["regions"].values()),d["provider_rows"])
        self.assertEqual(set(d),{"version","scope","as_of","source_database_sha256","public_manifest_sha256","provider_rows","sources","regions"})
        self.assertEqual(len(d["regions"]),56)
        for key,source in d["sources"].items():
            self.assertEqual(sum(row[key] for row in d["regions"].values()),source["rows"])
            self.assertEqual(set(source),{"release","rows","sha256"})
