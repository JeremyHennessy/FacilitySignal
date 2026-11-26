import tempfile
import unittest
from pathlib import Path
import openpyxl
from iqies_full_dictionary import extract, HEADER

class FullDictionaryTests(unittest.TestCase):
    def test_source_order_ambiguous_missing_and_provider_scoped_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"test.xlsx"
            w=openpyxl.Workbook();s=w.active;s.title="POS Data Dictionary"
            s.append(HEADER)
            s.append(["one","string","label","definition","ASC","M5"])
            s.append(["two","string","label","definition","ASC",None])
            s.append(["two","INT","other","definition","HHA",None])
            for i in range(1,13):
                s=w.create_sheet("M"+str(i));s.append(["ID","Value","Provider Type"])
                s.append(["1","A","ASC"]);s.append(["1","B","HHA"])
            w.save(p);w.close()
            r=extract(p,["two","one","three"],pinned=False)
            self.assertEqual(r["unique_matches"],1)
            self.assertEqual(r["unique_with_definition"],1)
            self.assertEqual(r["missing_fields"],["three"])
            self.assertEqual(r["ambiguous_fields"],["two"])
            self.assertEqual([x["field"] for x in r["fields"]],["two","one","three"])
            self.assertEqual(len(r["mapping_sheets"]["M5"]["entries"]),2)
            self.assertEqual(r["fields"][1]["candidates"][0]["mapping_status"],
                             "exact_mapping_sheet_reference")
            with self.assertRaises(ValueError):extract(p,["one"],pinned=True)
