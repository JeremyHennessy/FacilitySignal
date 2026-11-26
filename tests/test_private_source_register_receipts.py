"""The source register's current status is explicitly evidence-backed, not a publication grant."""
import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(name):return json.loads((ROOT/"research"/name).read_text())
class PrivateSourceRegisterReceiptTest(unittest.TestCase):
    def test_receipt_backed_statuses(self):
        plan=read("private_source_register_receipt_map_20261126.json");ledger=read("azure_archive_inventory_20261126.json")
        cov=read("coverage_status.json");overlay={x["id"]:x for x in cov["sources"]}
        original={x["id"] for x in read("facilitysignal_source_register_v0.2.json")["sources"]}
        self.assertEqual(len(plan["sources"]),15)
        for ident,rule in plan["sources"].items():
            with self.subTest(ident=ident):
                self.assertIn(ident,original);row=overlay[ident];self.assertEqual(row["status"],row["historical_qualification_status"])
                self.assertIn("historical_qualification_status",row)
                e=row["private_archive_evidence"];self.assertEqual(e["status"],rule["status"]);self.assertEqual(e["display_status"],rule["display_status"])
                pins=[x for x in ledger["receipts"] if x["key"].startswith(rule["prefix"])] if "prefix" in rule else [x for x in ledger["receipts"] if x["key"] in rule["keys"]]
                self.assertTrue(pins)
                self.assertEqual(e["receipt_keys"],sorted({x["key"] for x in pins}))
                self.assertEqual(e["release_observations"],sum(x["observations"] for x in pins if x["kind"] in ("publisher","supplemental_numeric")))
                self.assertEqual(e["aggregate_source_rows_screened"],sum(x["screened_observations"] for x in pins if x["kind"]=="aggregate"))
                self.assertFalse(e["public_promotion"]);self.assertEqual(e["consolidated_audit_run"],rule.get("consolidated_audit_run",plan["consolidated_audit_run"]))
                if "archive_readback_run" in rule:self.assertEqual(e["archive_readback_run"],rule["archive_readback_run"]);self.assertIn(e["archive_readback_run"],[p["run"] for p in pins])
    def test_crosswalk_receipt_scope(self):
        q=read("hcris_direct_measure_crosswalk_20261126.json")
        self.assertEqual(set(q["forms"]),{"hospital","snf"})
        self.assertFalse(q["monetary_scale_qualified"]);self.assertFalse(q["public_promotion"])
        for form,n in (("hospital",9),("snf",8)):
            r=q["forms"][form];self.assertEqual(len(r["measures"]),n)
            self.assertTrue(all(x["qualification"]=="matched_report_parity_supported" and not x["comparisons"].get("unequal_decimal") for x in r["measures"].values()))
            self.assertFalse(r["individual_values_retained"]);self.assertFalse(r["facility_financial_attribution"])
