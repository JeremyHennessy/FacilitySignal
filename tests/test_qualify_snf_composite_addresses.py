import json
import unittest

from scripts import qualify_snf_composite_addresses as q

CCN = "010101"
BEGIN, END = "09/30/2024", "09/30/2025"


def worksheet(flag="Y"):
    return {"flag": [flag], "ccn": [CCN], "begin": [BEGIN], "end": [END],
            "street": ["123 SAMPLE ROAD"], "city": ["SAMPLE CITY"], "state": ["AL"], "zip": ["00001"]}


def component(street="123 SAMPLE ROAD", zip_code="00001"):
    return {"name": ["NOT RETAINED"], "street": [street], "city": ["SAMPLE CITY"],
            "state": ["AL"], "zip": [zip_code], "po_box": ["998"]}


class SnfCompositeAddressTest(unittest.TestCase):
    def test_period_end_not_start_and_exact_report_worksheet_date(self):
        fields = worksheet()
        self.assertEqual(q.report_bounds((CCN, "1", BEGIN, END), fields)[1], "exact_header_identity_and_period")
        self.assertEqual(q.report_bounds((CCN, "1", BEGIN, "09/29/2025"), fields)[1],
                         "invalid_report_period_or_before_form_cutover")
        self.assertEqual(q.report_bounds((CCN, "1", "10/01/2024", END), fields)[1],
                         "header_and_worksheet_period_unresolved")
        self.assertEqual(q.report_bounds(("010102", "1", BEGIN, END), fields)[1],
                         "header_and_worksheet_ccn_unresolved")

    def test_negative_or_missing_flags_never_qualify_complete_cells(self):
        headers = {str(i): (CCN, "1", BEGIN, END) for i in range(1, 5)}
        fields = {"1": worksheet(), "2": worksheet("N"), "3": {**worksheet(), "flag": []},
                  "4": {**worksheet(), "flag": ["Y", "N"]}}
        locations = {k: {"01300": component()} for k in headers}
        result = q.summarize(headers, fields, locations)
        self.assertEqual(result["literal_composite_flag_report_counts"], {"Y": 1, "N": 1, "not_reported": 1, "duplicate": 1})
        self.assertEqual(result["literal_flag_and_cells"]["N_line13_groups_with_required_cells_populated"], 1)
        self.assertEqual(result["shape_qualified_address_observation_count"], 1)
        self.assertEqual(result["shape_qualified_address_comparison_to_printed_main"],
                         {"exact_same_printed_tuple_as_main": 1})
        self.assertEqual(result["known_ccns_with_y_and_n_reports"], 1)
        for unknown in (CCN, "123 SAMPLE ROAD", "SAMPLE CITY", "NOT RETAINED", BEGIN):
            self.assertNotIn(unknown, json.dumps(result))

    def test_civic_syntax_does_not_promote_postal_only_or_duplicate_columns(self):
        cases = [
            ({"street": [""]}, "po_box_only_or_missing_street"),
            ({"street": ["P.O. BOX 222"]}, "po_box_in_street"),
            ({"zip": ["N/A"]}, "unqualified_state_or_zip_shape"),
            ({"street": ["SAMPLE STREET"]}, "street_without_number_unresolved"),
            ({"zip": ["00001", "00002"]}, "duplicate_component_cell"),
        ]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                self.assertEqual(q.address_shape({**component(), **changes}), expected)
        self.assertEqual(q.address_shape(component(zip_code="00001-0090")), "complete_civic_shape")

    def test_full_subscript_and_period_conflicts_are_kept_not_merged(self):
        headers = {"1": (CCN, "1", BEGIN, END), "2": (CCN, "2", BEGIN, END)}
        data = {"1": {"01300": component(), "01301": component(street="456 SAMPLE ROAD")},
                "2": {"01300": component(street="789 SAMPLE ROAD")}}
        p = q.summarize(headers, {k: worksheet() for k in headers}, data)
        self.assertEqual(p["line13_subscript_groups"], {"base_01300": 2, "usages_of_full_nonbase_subscript": 1})
        self.assertEqual(p["repeated_y_provider_period_pairs"], 1)
        self.assertEqual(p["y_overlapping_period_pairs_with_different_nonempty_civic_sets"], 1)
        self.assertEqual(p["shape_qualified_address_distinct_ccn_count"], 1)
        self.assertEqual(p["shape_qualified_address_report_count"], 2)
        self.assertEqual(p["shape_qualified_address_observation_count"], 3)

    def test_line11_concordance_tier_and_cross_tab(self):
        keys = [str(i) for i in range(1, 6)]
        headers = {k: (CCN, "1", BEGIN, END) for k in keys}
        choices = (["Y"], ["N"], [], ["Y", "N"], ["Y"])
        fields = {k: {**worksheet(), "distinct_part_flag": f} for k, f in zip(keys, choices)}
        locations = {k: {"01300": component()} for k in keys}
        locations["5"]["01300"] = component(zip_code="NA")
        result = q.summarize(headers, fields, locations)
        self.assertEqual(result["literal_line11_distinct_part_for_line12_y_report_counts"],
                         {"Y": 2, "N": 1, "not_reported": 1, "duplicate": 1})
        self.assertEqual(result["literal_line11_flag_by_line12_y_address_quality"]["Y"],
                         {"complete_civic_shape": 1, "unqualified_state_or_zip_shape": 1})
        self.assertEqual(result["literal_line11_flag_by_line12_y_shape_comparison_to_printed_main"]["N"],
                         {"exact_same_printed_tuple_as_main": 1})
        self.assertEqual(result["both_flags_y_and_civic_shape"],
                         {"reports": 1, "observations": 1, "distinct_ccns": 1, "distinct_exact_tuples": 1})
        self.assertEqual(result["shape_qualified_observations_held_for_nonaffirmative_or_ambiguous_line11"], 3)

    def test_projector_uses_ccn_col3_and_exact_subscript(self):
        alpha = [["1", q.WORKSHEET, "00300", "00200", "NAME"],
                 ["1", q.WORKSHEET, "00300", "00300", CCN],
                 ["1", q.WORKSHEET, "01100", "00100", "Y"],
                 ["1", q.WORKSHEET, "01300", "00100", "ONE"],
                 ["1", q.WORKSHEET, "01301", "00100", "TWO"]]
        p, groups, n = q.load_fields(alpha)
        self.assertEqual((p["1"]["ccn"], n), ([CCN], 5))
        self.assertEqual(p["1"]["distinct_part_flag"], ["Y"])
        self.assertEqual(list(groups["1"]), ["01300", "01301"])

    def test_duplicate_report_header_is_rejected(self):
        header = ["1"] + [""] * 17
        with self.assertRaisesRegex(ValueError, "duplicate"):
            q.load_reports([header, header])
