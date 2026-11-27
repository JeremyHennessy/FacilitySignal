"""Address-only Minnesota campus regression fixtures; no provider or equipment rows."""
import unittest

import research_mn_boiler_location_candidates_20261127 as pilot


class CampusAttributionTests(unittest.TestCase):
    def assert_distinct_sites(self, a, b):
        for suffix in (False, True):
            with self.subTest(suffix=suffix):
                left = pilot.key(*a, suffix=suffix)
                right = pilot.key(*b, suffix=suffix)
                self.assertIsNotNone(left)
                self.assertIsNotNone(right)
                self.assertNotEqual(left, right)
                # Model candidate selection (not enrollment, asset or operator proof).
                indexed_site = {left: object()}
                self.assertNotIn(right, indexed_site)

    def test_fairview_west_bank_does_not_transfer_to_east_bank(self):
        self.assert_distinct_sites(
            ("2450 Riverside Avenue", "", "Minneapolis", "55454"),
            ("500 Harvard Street SE", "", "Minneapolis", "55455"),
        )

    def test_mayo_saint_marys_does_not_transfer_to_methodist(self):
        self.assert_distinct_sites(
            ("1216 Second Street SW", "", "Rochester", "55902"),
            ("201 W Center Street", "", "Rochester", "55902"),
        )

    def test_suffix_alias_can_preserve_site_but_not_swap_address(self):
        a = ("12 Sample Street SW", "", "Example", "55000")
        b = ("12 Sample St SW", "", "Example", "55000-1111")
        self.assertNotEqual(pilot.key(*a), pilot.key(*b))
        self.assertEqual(pilot.key(*a, suffix=True), pilot.key(*b, suffix=True))
        self.assertNotEqual(
            pilot.key(*a, suffix=True),
            pilot.key("12 Sample St SE", "", "Example", "55000", suffix=True),
        )

    def test_synthetic_offsite_reporting_closure_does_not_become_site_closure(self):
        # The pilot key has no reporting-status input; do not use it as a site filter.
        records = [
            ("independent_report", "12 Sample Street", "", "Example", "55000"),
            ("offsite_no_independent_report", "14 Sample Street", "", "Example", "55000"),
        ]
        for suffix in (False, True):
            keys = {status: pilot.key(*address, suffix=suffix) for status, *address in records}
            self.assertTrue(all(keys.values()))
            self.assertEqual(len(set(keys.values())), 2)

    def test_unresolved_second_address_line_is_held(self):
        self.assertIsNone(pilot.key("12 Sample Street", "West annex", "Example", "55000", True))


if __name__ == "__main__":
    unittest.main()
