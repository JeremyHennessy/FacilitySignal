"""Independent reconciliation of retained institutional observations with pinned evidence.
No Azure reads, source downloads, or public data release.
"""
from collections import Counter
import json
from pathlib import Path
import unittest
from institutional_observations import RULES

ROOT = Path(__file__).resolve().parents[1] / "research"

def read(name):
    return json.loads((ROOT / (name + "_20261126.json")).read_text(encoding="utf-8"))

class InstitutionalReceiptReconciliationTests(unittest.TestCase):
    def test_receipt_matches_qualified_source_domains(self):
        qualified = read("institutional_observations_qualification")
        prior = read("care_compare_infrastructure_qualification")
        profiles = {s["source"]: s for s in read("care_compare_directory_raw_field_profiles")["sources"]}
        inventory = read("azure_archive_inventory")
        self.assertEqual(set(qualified["sources"]), set(RULES))
        total = providers = field_count = 0
        for source, rules in RULES.items():
            obs = qualified["sources"][source]
            profile = profiles[source]
            self.assertEqual((obs["source_sha256"], obs["release"], obs["providers"]),
                             (profile["source_sha256"], profile["period"], profile["profiled_rows"]))
            self.assertEqual(set(obs["fields"]), set(rules))
            headers = {f["field"]: f for f in profile["fields"]}
            if source != "hospital":
                previous = prior["sources"][source]
                self.assertEqual((previous["sha256"], previous["rows"]),
                                 (obs["source_sha256"], obs["providers"]))
            for field, (header, domain, _) in rules.items():
                raw = headers[header]
                if source == "hospital":
                    literals = {k.capitalize(): v for k, v in raw["literal_yes_no_counts"].items()}
                else:
                    literals = {("" if k == "<blank>" else k): v
                                for k, v in previous["literal_counts"][header].items()}
                self.assertTrue(set(literals) <= set(domain))
                expected = Counter()
                for literal, n in literals.items():
                    expected[domain[literal]] += n
                self.assertEqual(dict(expected), obs["fields"][field])
                self.assertEqual(sum(expected.values()), obs["providers"])
                self.assertEqual(raw["states"].get("blank", 0), literals.get("", 0))
                total += sum(expected.values())
                field_count += 1
            self.assertEqual(obs["observations"], obs["providers"] * len(rules))
            providers += obs["providers"]
        self.assertEqual((total, providers, field_count),
                         (qualified["observations"], qualified["source_records"], qualified["field_rules"]))
        receipts = [r for r in inventory["receipts"] if r["kind"] == "institutional_fields"]
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["observations"], total)
        self.assertEqual(inventory["totals"]["derived_institutional_observations"], total)
