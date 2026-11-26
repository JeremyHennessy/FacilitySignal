import json
from pathlib import Path
import unittest
from scripts.postacute_raw_domain_audit import hha_reconciliation

ROOT=Path(__file__).resolve().parents[1]

class PostacuteRawReceiptTest(unittest.TestCase):
    def test_exact_pins_and_full_counts(self):
        r=json.loads((ROOT/"research/postacute_raw_domain_receipt_20261126.json").read_text())
        a=r["result"]
        pins={s["key"]:s for s in json.loads((ROOT/"research/snapshot_release_20261125.json").read_text())["sources"]}
        self.assertEqual(sum(s["rows"] for s in a["sources"]),8003)
        self.assertEqual(sum(s["headers"] for s in a["sources"]),37)
        for s in a["sources"]:
            n=s["rows"]; p=pins[s["source"]]
            self.assertEqual((s["source_sha256"],s["release"],n),(p["sha256"],p["release"],p["stored_rows"]))
            self.assertEqual(s["identity_projection_parity"],n)
            for k in ("ownership_states","certification_dates","region_states","region_counts","secondary_address","telephone_presence_only","ccn_shapes","zip_shapes"):
                self.assertEqual(sum(s[k].values()),n)
            self.assertEqual(sum(s["ownership_qualified_categories"].values()),sum(s["ownership_states"].get(k,0) for k in ("exact_trimmed","casefold_match")))
            self.assertEqual(s["region_states"],{"matches_reference":n})
            self.assertEqual(s["ownership_unmapped_distinct"],0)
            self.assertEqual(s["ownership_punctuation_candidates"],{})
        self.assertEqual(a["hha_reconciliation"],hha_reconciliation())
        self.assertEqual(a["publisher_bytes"],1039106)
        self.assertEqual(a["publisher_downloads"],3)
        self.assertEqual(a["new_application_approved_fields"],0)
        self.assertEqual(a["new_public_row_fields"],0)

    def test_date_and_capacity_exceptions_not_erased(self):
        a=json.loads((ROOT/"research/postacute_raw_domain_receipt_20261126.json").read_text())["result"]
        sources={s["source"]:s for s in a["sources"]}
        self.assertEqual(sources["rehabilitation"]["certification_dates"],{"valid_calendar_date":1220,"after_release":2})
        self.assertEqual(sources["long-term-hospital"]["secondary_address"],{"dash":311})
        self.assertEqual(sources["hospice"]["ownership_states"]["dash"],658)
        b=sources["long-term-hospital"]["beds"]
        self.assertEqual((b["reported"],b["sum"],b["min"],b["max"],b["zero"],b["existing_projection_parity"]),(305,21765,9,760,0,311))
        self.assertEqual(b["states"],{"reported_integer":305,"dash_marker":6})
