import csv
from collections import Counter
from datetime import date
from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile
import unittest
from scripts.hha_raw_domain_audit import audit, classify, load, relation

class HHARawDomainTest(unittest.TestCase):
    def test_pinned_scope(self):
        p,f=load()
        self.assertEqual((p["input_rows"],len(f)),(12409,96))
    def test_markers_and_zero(self):
        d=date(2026,10,21)
        self.assertEqual(classify("Not Available","rating",d),("not_available",None))
        self.assertEqual(classify("-","numerator",d),("dash",None))
        self.assertEqual(classify("0","numerator",d),("numeric_in_candidate_domain",Decimal(0)))
        self.assertEqual(classify("NaN","rating",d),("other_nonnumeric",None))
    def test_bounds(self):
        d=date(2026,10,21)
        for v,kind in [("0","rating"),("3.1","rating"),("5.5","rating"),("-1","numerator"),("1.5","denominator"),("100.01","reported_percentage")]:
            self.assertEqual(classify(v,kind,d)[0],"numeric_domain_review")
        self.assertEqual(classify("4.5","rating",d)[0],"numeric_in_candidate_domain")
        self.assertEqual(classify("0.4","observed_rate",d)[0],"numeric_scale_unresolved")
    def test_ownership_and_dates(self):
        d=date(2026,10,21)
        self.assertEqual(classify("Proprietary","control_category",d)[0],"documented:Proprietary")
        self.assertEqual(classify("other unknown","control_category",d)[0],"unmapped_category")
        self.assertEqual(classify("2/30/2025","date",d)[0],"invalid_calendar_date")
        self.assertEqual(classify("11/1/2026","date",d)[0],"date_after_release")
        self.assertEqual(classify("1/1/2025","date",d)[0],"calendar_date")
    def test_pairs(self):
        c=Counter()
        relation({70:Decimal(3),71:Decimal(2),73:Decimal("1"),74:Decimal("2"),75:Decimal("3")},(70,71,73,74,75),c)
        self.assertEqual(c["numerator_gt_denominator"],1)
        self.assertEqual(c["interval_order_review"],1)
        relation({70:Decimal(1)},(70,71,73,74,75),c)
        self.assertEqual(c["numerator_only"],1)
        self.assertEqual(c["interval_incomplete"],1)
    def test_fixture_reconciliation_and_no_raw_leak(self):
        _,f=load()
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"fixture.csv"
            row=[""]*96
            row[2]="SECRET_INSTITUTION_VALUE"
            row[7]="SECRET_UNKNOWN_CATEGORY"
            row[15]="4.5"
            row[17]="3"
            row[18]="2"
            with p.open("w",newline="",encoding="utf-8") as out:
                w=csv.writer(out);w.writerow([x["field"] for x in f]);w.writerow(row)
            pin={"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"release":"2026-10-21","input_rows":1,"stored_rows":1}
            r=audit(p,pin,f)
            self.assertEqual(r["ownership_unmapped_distinct"],1)
            self.assertEqual(r["pair_checks"]["18"]["numerator_gt_denominator"],1)
            self.assertNotIn("SECRET_",str(r))
            self.assertEqual(r["new_application_approved_fields"],0)
            with self.assertRaisesRegex(ValueError,"hash mismatch"):
                audit(p,{**pin,"sha256":"0"*64},f)
