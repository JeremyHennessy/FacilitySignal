import tempfile,unittest,zipfile
from pathlib import Path
from scripts.qualify_nppes_v2 import resolve,npi_valid,LABELS as ORIGINAL
from scripts.qualify_nppes_supplements import LABELS,scan_deactivation,inspect_deactivation,date_bucket

class NPPESSupplementTests(unittest.TestCase):
    def test_explicit_label_does_not_modify_original(self):
        label=LABELS["week_1102"]
        html='<a href="/nppes/synthetic.zip">'+label+'</a>'
        self.assertEqual(resolve(html,"weekly",publisher_label=label),"https://download.cms.gov/nppes/synthetic.zip")
        with self.assertRaises(ValueError):resolve(html,"weekly")
        self.assertIn("111626_112226",ORIGINAL["weekly"])
    def test_deactivation_no_identifier_retention(self):
        key=next("123456789"+str(i) for i in range(10) if npi_valid("123456789"+str(i)))
        rows=[["NPI","NPI Deactivation Date"],[key,"11/01/2026"],["bad",""],[key,"11/10/2026"]]
        a=scan_deactivation(iter(rows))
        self.assertEqual(a["key_validation_counts"],{"checksum_valid":2,"invalid_or_missing":1})
        self.assertEqual(a["deactivation_date_states"],{"on_or_before_release":1,"blank":1,"after_release":1})
        self.assertEqual(a["retained_identifiers"],0)
        self.assertIsNone(a["distinct_key_count"])
        self.assertNotIn(key,str(a))
        self.assertFalse(a["entity_type_available"])
    def test_archive_and_date_guard(self):
        key=next("123456789"+str(i) for i in range(10) if npi_valid("123456789"+str(i)))
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"source.zip"
            with zipfile.ZipFile(path,"w") as z:
                z.writestr("deactivation.csv","NPI,Deactivation Date\n"+key+",2026-11-01\n")
            a=inspect_deactivation(path)
            self.assertEqual(a["input_rows"],1)
            self.assertEqual(a["key_validation_counts"],{"checksum_valid":1})
        self.assertEqual(date_bucket("2026-02-30"),"invalid")
        with self.assertRaises(ValueError):scan_deactivation(iter([["NPI","Name","Deactivation Date"]]))

    def test_deactivation_field_name_separator_normalization(self):
        key=next("123456789"+str(i) for i in range(10) if npi_valid("123456789"+str(i)))
        for h in ("NPI_DEACTIVATION_DATE","DeactivationDate","deactivation-date"):
            a=scan_deactivation(iter([["NPI",h],[key,"2026-11-01"]]))
            self.assertEqual(a["key_validation_counts"],{"checksum_valid":1})
        with self.assertRaises(ValueError):scan_deactivation(iter([["NPI","Unrecognized Field"]]))

    def test_recognized_bounded_title_preamble(self):
        key=next("123456789"+str(i) for i in range(10) if npi_valid("123456789"+str(i)))
        a=scan_deactivation(iter([["NPPES Deactivated NPI Report - 11/09/2026"],[],["NPI","Deactivation Date"],[key,"11/01/2026"]]))
        self.assertEqual(a["header_ordinal"],3)
        self.assertEqual(a["preamble_counts"],{"bounded_metadata_cell":1,"blank":1})
        self.assertEqual(a["input_rows"],1)
        with self.assertRaises(ValueError):scan_deactivation(iter([[key],["NPI","Deactivation Date"]]))
        with self.assertRaises(ValueError):scan_deactivation(iter([["unexpected title"],["NPI","Deactivation Date"]]))

    def test_pinned_metadata_cell_still_rejects_possible_records(self):
        key=next("123456789"+str(i) for i in range(10) if npi_valid("123456789"+str(i)))
        header=["NPI","Deactivation Date"]
        a=scan_deactivation(iter([["Unrecognized metadata"],header,[key,"11/01/2026"]]),allow_pinned_preamble=True)
        self.assertEqual(a["preamble_counts"],{"bounded_metadata_cell":1})
        self.assertNotIn("Unrecognized metadata",str(a))
        for pre in ([key],[key,"11/01/2026"],["text "+key]):
            with self.assertRaises(ValueError):scan_deactivation(iter([pre,header]),allow_pinned_preamble=True)
