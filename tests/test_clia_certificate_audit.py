import unittest
from datetime import date
from clia_certificate_audit import parse_date,quantity,literal_code,scope,flag,ref_shape,classify_field
class CliaCertificateAuditTests(unittest.TestCase):
    def test_no_guessed_status(self):
        self.assertEqual(literal_code("00",{"00":"historical active"},True),"code_00")
        self.assertEqual(literal_code("18",{"00":"historical active"},True),"unmapped_code_18")
        self.assertEqual(literal_code("secret",{},True),"unrecognized")
        self.assertEqual(scope("unmapped_code_18"),"unresolved")
    def test_dates(self):
        self.assertEqual(parse_date("01/02/2026"),("ambiguous_slash",None))
        self.assertEqual(parse_date("13/02/2026")[1],date(2026,2,13))
        self.assertEqual(parse_date("2026-10-01")[0],"iso_after_release_end")
        self.assertEqual(parse_date("2026-02-30")[0],"invalid_calendar_date")
        self.assertEqual(parse_date("")[0],"blank")
    def test_states_and_reference_shape(self):
        self.assertEqual(quantity("0"),"zero")
        self.assertEqual(quantity(""),"blank")
        self.assertEqual(quantity("-1"),"negative")
        self.assertEqual(flag(""),"blank")
        self.assertEqual(ref_shape("12D1234567"),"clia_shaped")
        self.assertEqual(classify_field("PHNE_NUM")[0],"restricted_contact")
        self.assertEqual(classify_field("TRMNTN_EXPRTN_DT")[0],"date")
        with self.assertRaises(ValueError):classify_field("UNKNOWN_NEW_FIELD")
