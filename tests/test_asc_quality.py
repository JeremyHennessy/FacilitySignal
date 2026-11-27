import csv
import io
import unittest
from scripts import qualify_asc_quality as q

def data(rows, header=q.HEADER):
    stream=io.StringIO()
    writer=csv.writer(stream)
    writer.writerow(header)
    writer.writerows(rows)
    stream.seek(0)
    return stream

def row(ident="01C0001000", npi="1234567890", state="AL", year="2025"):
    return ["Fixture",ident,npi,"Town",state,"12345",year]+["Not Available"]+[""]*39

class ASCQualityTests(unittest.TestCase):
    def test_reconciles_presence_and_source_grain(self):
        self.assertEqual(len(q.HEADER),47)
        x=q.screen(data([row(),row(),row("", "", "XX", "")]),3)
        self.assertEqual(x["input_rows"],3)
        self.assertEqual(x["distinct_facility_year_keys"],1)
        self.assertEqual(x["repeated_facility_year_rows"],1)
        self.assertEqual(x["missing_or_unreviewed_facility_year_rows"],1)
        self.assertEqual(x["jurisdictions_represented"],1)
        self.assertEqual(x["field_presence_profiles"]["ASC-1 Rate*"],{"publisher_missing_literal":3})
        self.assertEqual(x["row_level_retained"],0)
        self.assertNotIn("01C0001000",str(x))
        self.assertNotIn("1234567890",str(x))
    def test_rejects_header_and_count_drift(self):
        with self.assertRaisesRegex(ValueError,"header"):
            q.screen(data([row()],list(reversed(q.HEADER))),1)
        with self.assertRaisesRegex(ValueError,"reconciliation"):
            q.screen(data([row()]),2)
        with self.assertRaisesRegex(ValueError,"width"):
            q.screen(data([row()[:-1]]),1)
    def test_separates_missing_from_populated_zero(self):
        self.assertEqual(q.state_of("0"),"populated")
        self.assertEqual(q.state_of("Not Applicable"),"publisher_missing_literal")
        self.assertEqual(q.state_of(" "),"blank")
