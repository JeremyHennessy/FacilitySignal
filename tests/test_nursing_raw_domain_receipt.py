from decimal import Decimal
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text())
class NursingRawDomainReceiptTest(unittest.TestCase):
    def test_pinned_aggregate_scope(self):
        r=read("research/nursing_raw_domain_receipt_20261127.json")
        a=r["result"]
        p=next(s for s in read("research/snapshot_release_20261125.json")["sources"] if s["key"]=="nursing")
        self.assertEqual((a["source_sha256"],a["release"],a["rows"],a["publisher_bytes"]),(p["sha256"],p["release"],p["stored_rows"],p["bytes"]))
        self.assertEqual((a["field_count"],a["identity_projection_parity"],a["publisher_downloads"]),(102,14686,1))
        for k in ("ownership_candidate_labels","provider_reported_categories","urban","hospital_location","ccrc","initial_approval_date","processing_date","coordinate_shape","coordinate_geocoding_footnote"):
            self.assertEqual(sum(a[k].values()),14686)
        self.assertEqual(len(a["ownership_candidate_labels"]),13)
        self.assertEqual(a["ownership_unmapped_distinct"],0)
        self.assertEqual(r["ownership_broad_candidate_groups"],{"for_profit":10885,"nonprofit":2853,"government":948})
        self.assertEqual(a["new_application_approved_fields"],0)
        self.assertEqual(a["new_public_row_fields"],0)
    def test_actual_capacity_and_footnote_checks(self):
        a=read("research/nursing_raw_domain_receipt_20261127.json")["result"]
        b=a["certified_beds"]; c=a["average_daily_residents"]
        self.assertEqual((b["reported"],b["sum"],b["min"],b["max"],b["zero"],b["public_projection_parity"]),(14675,1567009,2,843,0,14686))
        self.assertEqual(b["states"],{"blank":11,"reported":14675})
        self.assertEqual(c["states"],{"blank":58,"reported":14628})
        self.assertEqual(Decimal(c["sum"]),Decimal("1254183.5"))
        p=a["census_capacity_pairs"]
        self.assertEqual(sum(p[k] for k in ("both_reported","beds_only","census_only","neither_reported")),14686)
        self.assertEqual(p["both_reported"],14620)
        self.assertEqual(p["census_above_certified_beds"],122)
        self.assertEqual(p["census_above_certified_beds"]+p["census_at_or_below_certified_beds"],p["both_reported"])
        self.assertEqual(a["coordinate_geocoding_footnote"],{"within_global_bounds | 22":808,"within_global_bounds | blank":13878})
        prior=read("research/clinical_measure_quality_qualification_20261126.json")["sources"]["nursing"]["field_counts"]
        self.assertEqual(set(a["footnote_counts"]),set(prior))
        for field,counts in a["footnote_counts"].items():
            self.assertEqual(sum(counts.values()),14686)
            self.assertEqual(counts.get("blank",0),prior[field]["blank"])
            self.assertNotIn("unmapped_numeric_code",counts)
            self.assertNotIn("syntax_review",counts)
        self.assertEqual(a["footnote_counts"]["Geocoding Footnote"],{"22":808,"blank":13878})
        self.assertEqual(a["footnote_counts"]["Rating Cycle 1 Standard Survey Footnote"],{"29":129,"blank":14557})
        self.assertEqual(a["footnote_counts"]["Rating Cycle 2 Standard Survey Footnote"],{"29":4,"blank":14682})
