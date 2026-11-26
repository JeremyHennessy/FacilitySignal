"""Guard the coverage ledger against accidental count or qualification inflation."""
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"research"
def load(name):
    return json.loads((ROOT/name).read_text(encoding="utf-8"))

class SourceEvidenceCheckpointTests(unittest.TestCase):
    def test_inventory_and_ledger_reconcile(self):
        inventory=load("facilitysignal_source_register_v0.2.json")
        ledger=load("coverage_status.json")
        ids=[x["id"] for x in inventory["sources"]]
        actual=[x["id"] for x in ledger["sources"]]
        self.assertEqual(len(ids),176)
        self.assertEqual(len(set(ids)),len(ids))
        self.assertEqual(len(set(actual)),len(actual))
        self.assertEqual(set(ids),set(actual))
    def test_epa_is_not_qualified_or_loaded(self):
        ledger=load("coverage_status.json")
        row=next(x for x in ledger["sources"] if x["id"]=="FS-157")
        self.assertEqual(row["status"],"blocked_key_format_review")
        self.assertEqual(row["retrieved_rows"],434757)
        self.assertEqual(row["retrieved_rows"],row["documented_format_rows"]+row["unresolved_format_rows"])
        self.assertEqual(row["all_unique_nonblank_keys"],row["retrieved_rows"])
        self.assertEqual(row["duplicate_keys"]+row["blank_keys"]+row["trimmed_keys"],0)
        self.assertEqual(row["retained_database_rows"],0)
        self.assertEqual(row["reuse_review"],"pending")
    def test_date_and_release_reconciliation(self):
        ledger=load("coverage_status.json")
        date=ledger["national_date_normalization_qualified_baseline"]
        lock=load("snapshot_release_20261125.json")
        source=next(s for s in lock["sources"] if s["family"]=="registry" and s["key"]=="iqies")
        self.assertEqual(date["source_release_sha256"],source["sha256"])
        self.assertEqual(date["source_records"],lock["source_records_total"])
        self.assertEqual(date["status_observations"],source["stored_rows"])
        self.assertEqual(sum(date["date_state_counts"].values()),date["status_observations"])
        self.assertEqual(date["date_state_counts"],{"reported":15803,"ambiguous":9765,"not_available":74766})
        self.assertEqual(date["candidate_pairs"]+date["unmatched_facility_source_rows"],48004)
        self.assertLessEqual(date["same_state_type_address_city_zip_pairs"],date["candidate_pairs"])
