import json
import unittest
from scripts.hospital_ltch_address_adjudication import classify, qualified


def row(address, **extra):
    return {"ccn": "001", "name": "Example Hospital", "address": address, "city": "Example", "state": "NY", "zip": "10001", **extra}


class HospitalLtchAdjudicationTests(unittest.TestCase):
    def test_exact_terminal_hyphen_only(self):
        self.assertEqual(classify(row("10 Main St, Suite 2"), row("10 MAIN ST, SUITE 2 -")), "ltch_terminal_hyphen_only")
        self.assertEqual(classify(row("10 Main St"), row("10 Main St")), "exact_reported_address")

    def test_not_general_address_rewriting(self):
        for address in ("10 Main Street -", "10 Main St, Suite 3 -", "10 Main St-", "10 Main St - -", "11 Main St -"):
            self.assertEqual(classify(row("10 Main St"), row(address)), "other_street_discrepancy")
        self.assertEqual(classify(row("10 Main St -"), row("10 Main St")), "other_street_discrepancy")
        self.assertEqual(classify(row("10 Main St"), row("10 Main St -", zip="10002")), "city_state_or_zip_discrepancy")
        self.assertEqual(classify(row("10 Main St"), row("10 Main St -", name="Different")), "name_discrepancy")
        self.assertEqual(classify(row("10 Main St"), row("10 Main St -", ccn="002")), "different_identifier")
        self.assertEqual(classify(row("10 Main St"), row("")), "incomplete_address")

    def test_pinned_actual_reconciliation(self):
        result = qualified()
        self.assertEqual(result["canonical_merges"], 0)
        self.assertEqual(sum(result["classification_counts"].values()), result["shared_ccn_pairs"])
        print("FACILITYSIGNAL_HOSPITAL_LTCH_ADJUDICATION", json.dumps(result, sort_keys=True), flush=True)
