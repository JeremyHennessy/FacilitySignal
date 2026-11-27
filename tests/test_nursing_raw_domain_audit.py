from datetime import date
from decimal import Decimal
import unittest
from scripts.nursing_raw_domain_audit import category, OWNERS, PROVIDERS, decimal_value, date_state, footnote, coordinate_state, audit_rows

class NursingRawDomainTests(unittest.TestCase):
    def test_label_candidates_and_unknowns(self):
        self.assertEqual(category(" For profit - Corporation ",OWNERS),"for_profit_corporation")
        self.assertEqual(category("Medicare and Medicaid",PROVIDERS),"medicare_and_medicaid")
        self.assertEqual(category("UNKNOWN_OWNER_STRING",OWNERS),"unmapped")
        self.assertEqual(category("",OWNERS),"blank")
    def test_numeric_types(self):
        self.assertEqual(decimal_value("0"),("reported",Decimal(0)))
        self.assertEqual(decimal_value(""),("blank",None))
        self.assertEqual(decimal_value("-1"),("domain_review",None))
        self.assertEqual(decimal_value("1.5",integer=True),("domain_review",None))
        self.assertEqual(decimal_value("NaN"),("syntax_review",None))
    def test_dates_footnotes_geography(self):
        r=date(2026,10,28)
        self.assertEqual(date_state("2024-02-29",r),"calendar_date")
        self.assertEqual(date_state("2025-02-29",r),"calendar_review")
        self.assertEqual(date_state("2026-10-29",r),"after_release")
        self.assertEqual(footnote("29"),"29")
        self.assertEqual(footnote("13, 23"),"13+23")
        self.assertEqual(footnote("99"),"unmapped_numeric_code")
        self.assertEqual(footnote("SECRET_VALUE"),"syntax_review")
        self.assertEqual(coordinate_state("91","0"),"outside_global_bounds")
        self.assertEqual(coordinate_state("0","0"),"zero_pair_review")
        self.assertEqual(coordinate_state("44","-63"),"within_global_bounds")
    def test_audit_aggregate_no_raw_values(self):
        ident={"ccn":"123456","name":"FIXTURE_NAME","address":"FIXTURE_ADDRESS","city":"CITY","state":"NY","zip":"12345"}
        row={"Ownership Type":"SECRET_UNKNOWN_OWNER","Provider Type":"Medicare","Urban":"Y","Provider Resides in Hospital":"N","Continuing Care Retirement Community":"N","Date First Approved to Provide Medicare and Medicaid Services":"2025-01-01","Processing Date":"2026-10-01","Number of Certified Beds":"12","Average Number of Residents per Day":"13.5","Latitude":"44.12345","Longitude":"-63.12345","Geocoding Footnote":"22"}
        note_fields=["Geocoding Footnote"]+["test_note_"+str(i) for i in range(14)]
        row.update({f:"" for f in note_fields[1:]})
        fields=[{"field":f,"kind":"footnote"} for f in note_fields]
        rows={("123456","NY"):(row,ident)}
        pin={"key":"nursing","release":"2026-10-28","sha256":"a"*64}
        shard={"source":"nursing","release":pin["release"],"row_count":1,"records":[{**ident,"capacity":"12"}]}
        r=audit_rows(rows,pin,shard,fields)
        self.assertEqual(r["ownership_unmapped_distinct"],1)
        self.assertEqual(r["census_capacity_pairs"]["census_above_certified_beds"],1)
        self.assertEqual(r["footnote_counts"]["Geocoding Footnote"],{"22":1})
        self.assertEqual(r["new_public_row_fields"],0)
        for x in ("FIXTURE_NAME","FIXTURE_ADDRESS","SECRET_UNKNOWN_OWNER","44.12345","-63.12345","123456"):
            self.assertNotIn(x,str(r))
        with self.assertRaises(ValueError):
            audit_rows(rows,pin,{**shard,"records":[{**ident,"capacity":"13"}]},fields)
