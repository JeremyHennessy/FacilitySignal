import unittest
from scripts.qualify_nursing_chain_projection import qualify
class NursingChainProjectionTests(unittest.TestCase):
    def test_membership_exact_and_missing(self):
        rows={};records=[]
        for n in range(3):
            ccn=f"{n+1:06d}";record={"ccn":ccn,"name":"Example "+str(n),"address":"1 Main","city":"Town","state":"NY","zip":"00001","capacity":"50"}
            records.append(record);raw={"Chain ID":"123" if n<2 else "","Number of Facilities in Chain":"2" if n<2 else "","Chain Name":"Example Group" if n<2 else ""}
            rows[(ccn,"NY")]=(raw,{k:v for k,v in record.items() if k!="capacity"})
        pin={"key":"nursing","release":"2026-10-28"};shard={"source":"nursing","release":"2026-10-28","row_count":3,"records":records}
        links,groups,audit=qualify(shard,pin,rows)
        self.assertEqual(links,{"NY:000001":"123","NY:000002":"123"})
        self.assertEqual(groups,{"123":2});self.assertEqual(audit["missing_group_records"],1)
        self.assertNotIn("Example Group",str(links)+str(groups)+str(audit))
        rows[("000001","NY")][0]["Number of Facilities in Chain"]="3"
        with self.assertRaises(ValueError):qualify(shard,pin,rows)
