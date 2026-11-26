import unittest
from decimal import Decimal
from scripts.qualify_hcris_capacity_candidate import candidate_records,summarize,integer_or_missing
class CapacityCandidateTest(unittest.TestCase):
    def test_values_and_scope(self):
        self.assertIsNone(integer_or_missing(None));self.assertEqual(integer_or_missing(Decimal("0")),0)
        for v in ("-1","2.5","9007199254740992"):
            with self.assertRaises(ValueError):integer_or_missing(Decimal(v))
    def test_exact_projection_no_monetary(self):
        h={"1":("012345","1/7/2024","12/31/2024"),"2":("012346","1/7/2024","12/31/2024")}
        p={k:(v[0],"NY",v[1],v[2]) for k,v in h.items()}
        a={k:{"ccn":[v[0]],"state":["NY"],"begin":[v[1]],"end":[v[2]]} for k,v in h.items()}
        a["2"]["state"]=["NJ"]
        d={"012345":{"NY":1},"012346":{"NY":1}}
        vals={"1":{"Number of Beds":(Decimal(50),"positive"),"Total Bed Days Available":(None,"blank"),"Total Costs":(Decimal(999),"positive")}}
        r=candidate_records(h,p,a,d,vals,"snf")
        self.assertEqual(len(r),1);self.assertEqual(r[0]["measures"],{"available_beds_at_period_end":50,"available_bed_days":None})
        receipt=summarize(r,"snf",{"nonconflicting_three_way_candidate_reports":1,"candidate_provider_records":1})
        self.assertEqual(receipt["field_value_states"]["available_bed_days"],{"missing":1})
        self.assertFalse(receipt["row_level_output_retained"])
        self.assertNotIn("012345",str(receipt))
