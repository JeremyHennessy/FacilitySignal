import unittest
from scripts.qualify_cms_reh_op18 import qualify

ROWS=[(f"REH_OP_18{g}{s}",label,v,"","01/01/2025","12/31/2025") for g in "abcd"
      for s,label,v in (("","Average (median) fixture","100"),("_NINETIETH","Top ten percent fixture","90"))]

class TestDisplay(unittest.TestCase):
    def test_roles_not_patient_quantile(self):
        r=qualify(ROWS,"2026-11-12")
        self.assertEqual(r["reported_pair_order_counts"],{"top_label_lower":4})
        self.assertEqual(r["patient_wait_quantiles_derived"],0)

    def test_reject_shape_label_and_period_drift(self):
        for changed in (ROWS[:-1],ROWS[:-1]+ROWS[:1],
                        ROWS[:-1]+[(*ROWS[-1][:1],"Patient percentile",*ROWS[-1][2:])],
                        ROWS[:-1]+[(*ROWS[-1][:2],"Not Available",*ROWS[-1][3:])],
                        ROWS[:-1]+[(*ROWS[-1][:-1],"01/31/2026")]):
            with self.subTest(changed=changed),self.assertRaises(ValueError):
                qualify(changed,"2026-11-12")
        with self.assertRaises(ValueError):
            qualify(ROWS,"2026-05-13")

if __name__=="__main__":
    unittest.main()
