import unittest
from decimal import Decimal
from scripts.qualify_procurement_awards import audit,AGENCY,FIELDS
class ProcurementTests(unittest.TestCase):
    def row(self,key="source-award"):
        return {"Award ID":"fixture","generated_internal_id":key,"Awarding Agency":AGENCY,"Awarding Sub Agency":"fixture","Start Date":"2026-10-01","End Date":None,"Award Amount":Decimal("0"),"Contract Award Type":"fixture","Place of Performance State Code":"NY","Place of Performance Country Code":"USA","Recipient UEI":"ABC123DEF456"}
    def test_audit_minimal_aggregate(self):
        d=audit({"results":[self.row()],"page_metadata":{"page":1,"hasNext":True}})
        self.assertEqual(d["sample_rows"],1)
        self.assertEqual(d["amount_value_states"],{"zero":1})
        self.assertEqual(d["confirmed_active_opportunities"],0)
        self.assertNotIn("source-award",str(d));self.assertNotIn("ABC123DEF456",str(d))
    def test_fail_closed(self):
        for rows in ([self.row(),self.row()],[{**self.row(),"Awarding Agency":"Other"}],[{k:v for k,v in self.row().items() if k!="Award ID"}],[]):
            with self.assertRaises(ValueError):audit({"results":rows,"page_metadata":{"page":1,"hasNext":False}})
