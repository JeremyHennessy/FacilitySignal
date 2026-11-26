import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/"research"
class HCRISQualificationLedgerTests(unittest.TestCase):
    def test_partial_form_grain_and_parent_links(self):
        l=json.loads((ROOT/"coverage_status.json").read_text())
        row=next(x for x in l["sources"] if x["id"]=="FS-055")
        b=l["hcris_hha_structural_baseline"];a=b["audit"];t=a["tables"]
        self.assertEqual(row["status"],"partial_structural_qualification")
        self.assertEqual((a["form"],a["fiscal_year"]),("CMS-1728-20",2024))
        self.assertEqual(t["report"]["rows"],11009)
        self.assertEqual(t["report"]["distinct_report_keys"],11009)
        self.assertEqual(t["report"]["invalid_report_key_rows"]+t["report"]["duplicate_report_key_rows"],0)
        for role,n in (("numeric",3558558),("alpha",1222130)):
            x=t[role]
            self.assertEqual(x["rows"],n)
            self.assertEqual(x["report_key_link_counts"],{"report_present":n})
            self.assertEqual(x["coordinate_shape_counts"],{"shape_valid":n})
            self.assertEqual(sum(x["coordinate_class_counts"].values()),n)
        self.assertEqual(t["numeric"]["coordinate_class_counts"]["alphanumeric_column"],239322)
        self.assertEqual(t["alpha"]["coordinate_class_counts"]["worksheet_heading"],312617)
        self.assertEqual(row["retained_database_rows"],0)
        self.assertFalse(b["included_in_integrated_national_baseline"])
        self.assertFalse(b["included_in_expanded_projection_total"])
        self.assertEqual(json.loads((ROOT/"expanded_source_lock_20261126.json").read_text())["source_count"],17)
    def test_fda_access_blocked_not_qualified(self):
        l=json.loads((ROOT/"coverage_status.json").read_text())
        row=next(x for x in l["sources"] if x["id"]=="FS-077")
        b=l["fda_503b_access_blocker"]
        self.assertEqual(row["status"],"blocked_publisher_access")
        self.assertEqual(row["retrieved_rows"],0)
        self.assertEqual(b["retry_http_status"],401)
        self.assertFalse(b["qualified"])
