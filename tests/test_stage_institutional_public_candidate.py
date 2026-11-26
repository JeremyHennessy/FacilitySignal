import copy
import unittest
from scripts import stage_institutional_public_candidate as stage

class InstitutionalPublicStageTests(unittest.TestCase):
    def setUp(self):
        self.pack={"format_version":1,"scope":stage.SCOPE,"sources":{}}
        self.expected={}
        self.dirs={}
        self.pins={}
        for source,fields in stage.FIELDS.items():
            self.dirs[source]={"records":[{"ccn":"000001","state":"NY"}]}
            self.pins[source]={"release":"2026-10-28","sha256":"a"*64,"rows":1}
            self.expected[source]={"providers":1,"source_sha256":"b"*64,"fields":{field:{"reported_yes":1} for field in fields}}
            self.pack["sources"][source]={"release":"2026-10-28","directory_sha256":"a"*64,"source_sha256":"b"*64,"fields":list(fields),"records":[["000001","NY",*(["reported_yes"]*len(fields))]]}
    def test_exact_scope(self):
        self.assertEqual(stage.validate_pack(self.pack,self.expected,self.dirs,self.pins),7)
    def test_forbid_safety_field(self):
        self.pack["sources"]["nursing"]["fields"].append("sprinklers")
        self.pack["sources"]["nursing"]["records"][0].append("all_required_areas")
        with self.assertRaises(ValueError):stage.validate_pack(self.pack,self.expected,self.dirs,self.pins)
    def test_reject_changed_membership_values_and_metadata(self):
        for key,value in (("source_sha256","c"*64),("release","2025-01-01"),("private_data","bad")):
            x=copy.deepcopy(self.pack);x["sources"]["hospital"][key]=value
            with self.assertRaises(ValueError):stage.validate_pack(x,self.expected,self.dirs,self.pins)
        for row in (["000002","NY","reported_yes"],["000001","NY","reported_no"],["000001","NY","not_available"]):
            x=copy.deepcopy(self.pack);x["sources"]["hospital"]["records"]=[row]
            with self.assertRaises(ValueError):stage.validate_pack(x,self.expected,self.dirs,self.pins)
    def test_duplicate_record(self):
        self.pack["sources"]["hospital"]["records"]*=2
        with self.assertRaises(ValueError):stage.validate_pack(self.pack,self.expected,self.dirs,self.pins)
