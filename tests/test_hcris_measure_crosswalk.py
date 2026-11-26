import unittest,hashlib
from decimal import Decimal
from collections import defaultdict
from scripts.qualify_hcris_measure_crosswalk import compare,parse_puf,MAPS
class CrosswalkTest(unittest.TestCase):
    def test_exact_comparison_and_duplicate_exclusion(self):
        m={"Total Costs":("C000001","20200","00300","monetary_source_value")}
        p={str(x):1 for x in range(1,8)}
        r={str(x):{"Total Costs":(Decimal("10") if x in (1,2,3,7) else None,"positive" if x in (1,2,3,7) else "blank")} for x in range(1,7)}
        f={"Total Costs":{"1":[(Decimal("10.00"),"positive")],"2":[(Decimal("9"),"positive")],"3":[(Decimal("10"),"positive"),(Decimal("10"),"positive")],"4":[(Decimal("0"),"zero")],"5":[(None,"blank")]}}
        a=compare(m,p,r,f)
        self.assertEqual(a["archive_only_report_keys"],1);c=a["measures"]["Total Costs"]["comparisons"]
        self.assertEqual(c,{"ambiguous_multiple_cells":1,"both_explicit_missing":1,"equal_decimal":1,"puf_missing_archive_absent":1,"puf_missing_archive_explicit_zero":1,"unequal_decimal":1})
        self.assertEqual(a["measures"]["Total Costs"]["qualification"],"review_required")
    def test_parse_exact_puf(self):
        data=b"rpt_rec_num,Number of Beds\n0001,2\n0002,\n"
        a={"bytes":len(data),"source_sha256":hashlib.sha256(data).hexdigest(),"columns":2,"stored_rows":2,"input_rows":2,"measure_value_states":{"Number of Beds":{"positive":1,"blank":1}}}
        m={"Number of Beds":MAPS["hospital"]["Number of Beds"]}
        r=parse_puf(data,a,m);self.assertEqual(r["0001"]["Number of Beds"],(Decimal(2),"positive"))
        with self.assertRaises(ValueError):parse_puf(data+b"\n",a,m)
    def test_catalog_direct_coordinates(self):
        self.assertEqual(MAPS["hospital"]["Total Costs"][:3],("C000001","20200","00300"))
        self.assertEqual(MAPS["hospital"]["Depreciation Cost"][:3],("A700003","00300","00900"))
        self.assertEqual(len(MAPS["hospital"])+len(MAPS["snf"]),17)
