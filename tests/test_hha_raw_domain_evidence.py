import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class HHARawDomainEvidenceTest(unittest.TestCase):
    def test_logged_counts_reconcile(self):
        r=json.loads((ROOT/"research/hha_raw_domain_log_summary_20261126.json").read_text())
        a=r["observations"]; n=a["rows"]
        self.assertEqual((n,a["fields"],len(a["pairs"])),(12409,96,16))
        for f in ("date","ownership","rating"):
            self.assertEqual(sum(a[f].values()),n)
        for p in a["pairs"].values():
            self.assertEqual(sum(p.get(k,0) for k in ("both_counts_numeric","numerator_only","denominator_only","neither_count_numeric")),n)
            self.assertEqual(p.get("numerator_le_denominator",0)+p.get("numerator_gt_denominator",0),p["both_counts_numeric"])
            if "interval_all_numeric" in p:
                self.assertEqual(p["interval_all_numeric"]+p["interval_incomplete"],n)
                self.assertEqual(p["interval_ordered"]+p.get("interval_order_review",0),p["interval_all_numeric"])
        for k,v in r["pair_totals"].items():
            self.assertEqual(v,sum(p.get(k,0) for p in a["pairs"].values()))
        self.assertEqual(a["rating"],{"dash":4283,"numeric_in_candidate_domain":8126})
        self.assertEqual(a["ownership"],{"dash":2167,"unmapped_category":10242})
        self.assertEqual(r["new_application_approved_fields"],0)
        self.assertEqual(r["new_public_row_fields"],0)
