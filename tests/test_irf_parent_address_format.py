import json
import unittest
from scripts import qualify_irf_parent_address_format as q
from scripts import qualify_irf_parent_candidates as parent

def row(ccn, address="12 A St.", city="Some City", zip="01234", state="AL"):
    return dict(ccn=ccn, address=address, city=city, zip=zip, state=state)

class IRFAddressFormatAudit(unittest.TestCase):
    def test_format_only_not_address_identity(self):
        source=[row("21T101"), row("21T102"), row("21T103"), row("21T104"), row("21T105")]
        targets=[row("210101", "12 a st", "SOME-CITY"), row("210102", zip="1234"),
                 row("210103"), row("210103"), row("210104", address=""),
                 row("210105", state="NY")]
        self.assertEqual(q.audit_rows(source, targets)["T"], {
            "total":5, "exact_address_context":0, "format_only_address_context":1,
            "different_context":2, "multiple":1, "missing_or_conflict":1})
    def test_nonblank_and_no_abbreviation_inference(self):
        self.assertFalse(q.format_equal({"address":""}, {"address":"."}, ("address",)))
        self.assertFalse(q.format_equal({"address":"12 Main Street"}, {"address":"12 Main St"}, ("address",)))
    def test_reproduce_exact_projection_aggregate(self):
        path=parent.ROOT/"research/fs043_irf_address_format_audit_20261128.json"
        evidence=json.loads(path.read_text())
        self.assertEqual(q.audit(), evidence["aggregate"])
        self.assertEqual(sum(x["total"] for x in evidence["aggregate"].values()),810)
        self.assertEqual(evidence["confirmed_parent_links"],0)
