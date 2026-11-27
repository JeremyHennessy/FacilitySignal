"""Release projection of already-committed national aggregates; no provider records."""
import copy
import json
import unittest

from scripts.build_public_intelligence import (
    IQIES_SERVICE_RECEIPT, IQIES_SERVICE_RUN, ROOT, iqies_service_groups, read,
)


class IqiesServicePublicAggregateTests(unittest.TestCase):
    def setUp(self):
        self.input = read(IQIES_SERVICE_RECEIPT)
        self.pin = next(row for row in read(ROOT/"research/snapshot_release_20261125.json")["sources"]
                        if row["key"] == "iqies")

    def test_two_groups_reconcile_and_preserve_meanings(self):
        asc, esrd = iqies_service_groups(self.input, self.pin)
        self.assertEqual([asc["id"],esrd["id"]],["iqies-additional-asc","iqies-additional-esrd"])
        self.assertEqual([len(asc["rows"]),len(esrd["rows"])],[8,3])
        for group, eligible, missing in [(asc,8492,452),(esrd,8659,212)]:
            self.assertEqual(group["run"],IQIES_SERVICE_RUN)
            self.assertIn("Not available is not No",group["note"])
            self.assertTrue(all(row[1]==eligible==sum(row[2:]) and row[-1]==missing for row in group["rows"]))
        self.assertEqual(esrd["rows"][0],["Began in-center nocturnal hemodialysis",8659,12,8435,212])
        self.assertIn("does not rule out an established service",esrd["note"])
        self.assertTrue(all(row[0].startswith("Continued providing") for row in esrd["rows"][1:]))
        self.assertEqual(sum(row[1] for g in [asc,esrd] for row in g["rows"]),93913)

    def test_does_not_publish_private_identifiers_or_metadata(self):
        receipt=self.input["receipt"]
        before=iqies_service_groups(self.input,self.pin)
        receipt["private_rows"]=[{"provider_id":"DO_NOT_PUBLISH","name":"PRIVATE"}]
        receipt["address"]="PRIVATE"
        self.assertEqual(iqies_service_groups(self.input,self.pin),before)
        serialized=json.dumps(before)
        for blocked in ["DO_NOT_PUBLISH","PRIVATE","row_number","provider_id","CCN","sha256"]:
            self.assertNotIn(blocked,serialized)

    def test_rejects_wrong_pin_period_extra_field_or_missing_as_no(self):
        for field,value in [("source_period","2026-10-01/2026-12-31"),("source_sha256","wrong"),
                            ("dictionary_sha256","wrong"),("source_record_filter_checks",32)]:
            with self.subTest(field=field):
                wrong=copy.deepcopy(self.input)
                wrong["receipt"][field]=value
                with self.assertRaises(ValueError):
                    iqies_service_groups(wrong,self.pin)
        wrong=copy.deepcopy(self.input)
        wrong["receipt"]["field_states"]["provider_id"]={}
        with self.assertRaises(ValueError):
            iqies_service_groups(wrong,self.pin)
        wrong=copy.deepcopy(self.input)
        field=wrong["receipt"]["field_states"]["ft_srgry_sw"]
        field["reported_no"]+=field["not_available"]
        field["not_available"]=0
        with self.assertRaises(ValueError):
            iqies_service_groups(wrong,self.pin)

if __name__=="__main__":
    unittest.main()
