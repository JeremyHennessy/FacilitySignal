import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import build_nursing_chain_pack as m

class NursingChainTests(unittest.TestCase):
    def setUp(self):
        self.directory={"records":[{"ccn":"000001","state":"NY"},{"ccn":"000002","state":"NY"},{"ccn":"000003","state":"CA"}]}
        self.pack={"format_version":1,"scope":m.SCOPE,"source":"nursing","release":m.RELEASE,"source_sha256":m.SOURCE,"directory_sha256":m.DIRECTORY,"groups":[["007","EXAMPLE CHAIN",2]],"members":[["000001","NY","007"],["000002","NY","007"],["000003","CA",None]]}
        self.counts=patch.object(m,"COUNTS",{"groups":1,"assigned":2,"unassigned":1,"providers":3})
        self.bands=patch.object(m,"BANDS",{"2-4":1})
        self.counts.start();self.bands.start();self.addCleanup(self.counts.stop);self.addCleanup(self.bands.stop)
    def test_exact_group(self):
        self.assertEqual(m.validate(self.pack,self.directory)["assigned"],2)
    def test_fail_closed(self):
        for mutate in (
            lambda p:p["members"].append(p["members"][0]),
            lambda p:p["members"].__setitem__(1,p["members"][0]),
            lambda p:p["members"][0].__setitem__(2,None),
            lambda p:p["members"][0].__setitem__(1,"CA"),
            lambda p:p["groups"][0].__setitem__(2,3),
            lambda p:p["groups"][0].append("owner name"),
            lambda p:p["groups"][0].__setitem__(0,"7.0"),
            lambda p:p.__setitem__("release","2026-12-02"),
            lambda p:p.__setitem__("private_rows",[]),
        ):
            p=copy.deepcopy(self.pack);mutate(p)
            with self.subTest(p=p),self.assertRaises(ValueError):m.validate(p,self.directory)
