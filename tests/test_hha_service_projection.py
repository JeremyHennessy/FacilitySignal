import unittest
from scripts.qualify_hha_service_projection import qualify,SERVICES
class HomeHealthProjectionTests(unittest.TestCase):
    def test_dash_and_no_are_distinct(self):
        r={"ccn":"000001","name":"Example","address":"1 Main","city":"Town","state":"NY","zip":"00001","capacity":""}
        original={"Offers "+label+" Services":"Yes" if label==SERVICES[0] else "No" if label==SERVICES[1] else "-" for label in SERVICES}
        rows={("000001","NY"):(original,{k:v for k,v in r.items() if k!="capacity"})}
        expected={label:{"yes":int(label==SERVICES[0]),"no":int(label==SERVICES[1]),"other_states":{"dash_marker":1} if label not in SERVICES[:2] else {}} for label in SERVICES}
        pin={"key":"home-health","release":"2026-10-21"};shard={"source":"home-health","release":"2026-10-21","row_count":1,"records":[r]}
        records,counts=qualify(shard,pin,rows,expected)
        self.assertEqual(records["NY:000001"][SERVICES[0]],"yes")
        self.assertEqual(records["NY:000001"][SERVICES[1]],"no")
        self.assertEqual(records["NY:000001"][SERVICES[2]],"dash_marker")
        self.assertEqual(set(records["NY:000001"]),set(SERVICES))
        with self.assertRaises(ValueError):qualify({**shard,"release":"wrong"},pin,rows,expected)
        with self.assertRaises(ValueError):qualify({**shard,"records":[{**r,"address":"Different"}]},pin,rows,expected)
