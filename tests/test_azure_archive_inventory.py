import copy,json,unittest
from scripts import audit_azure_archive_inventory as audit

class ArchiveInventoryTests(unittest.TestCase):
    def setUp(self): self.ledger=json.loads(audit.LEDGER.read_text())
    def test_counts_and_grain(self):
        t=audit.totals(self.ledger)
        self.assertEqual(t["publisher_releases"],55)
        self.assertEqual(t["source_observations"],117850515)
        self.assertEqual(t["derived_candidate_observations"],23520)
        self.assertEqual(t["payload_files"],202)
        self.assertEqual(t["supplemental_numeric_archives"],41)
        self.assertEqual(t["supplemental_numeric_observations"],107619587)
        self.assertEqual(t["aggregate_evidence_releases"],6)
        self.assertEqual(t["aggregate_source_rows_screened"],40564158)
    def test_reject_duplicate_release(self):
        self.ledger["receipts"].append(copy.deepcopy(self.ledger["receipts"][0]))
        with self.assertRaises(Exception): audit.totals(self.ledger)
    def test_reject_derived_as_publisher(self):
        next(x for x in self.ledger["receipts"] if x["kind"]=="derived")["kind"]="publisher"
        with self.assertRaises(Exception): audit.totals(self.ledger)
    def test_reject_byte_count_drift(self):
        self.ledger["receipts"][0]["files"][0]["bytes"]+=1
        with self.assertRaises(Exception): audit.totals(self.ledger)
    def test_read_only(self):
        store=audit.ReadOnlyAzure.__new__(audit.ReadOnlyAzure)
        with self.assertRaises(ValueError): store.create("anything",None,1,"text/plain")
        with self.assertRaises(ValueError): store.delete_probe("anything","etag")

    def test_supplemental_projection_requires_parent_and_not_new_publisher(self):
        parent=next(x for x in self.ledger["receipts"] if x["key"]=="hcris-cmhc-2017-index")
        existing=next((x for x in self.ledger["receipts"] if x["key"]=="hcris-cmhc-2017-numeric"),None)
        if existing:
            self.ledger["receipts"].remove(existing)
            t=self.ledger["totals"];t["source_observations"]-=existing["observations"];t["supplemental_numeric_archives"]-=1;t["supplemental_numeric_observations"]-=existing["observations"];t["payload_files"]-=len(existing["files"]);t["payload_bytes"]-=sum(f["bytes"] for f in existing["files"])
        p=copy.deepcopy(parent);p.update(key="hcris-cmhc-2017-numeric",kind="supplemental_numeric",observations=2,parent_database_sha256=next(f["sha256"] for f in parent["files"] if f["path"]=="projection.sqlite3"))
        self.ledger["receipts"].append(p)
        t=self.ledger["totals"];t["source_observations"]+=2;t["supplemental_numeric_archives"]+=1;t["supplemental_numeric_observations"]+=2;t["payload_files"]+=2;t["payload_bytes"]+=sum(f["bytes"] for f in p["files"])
        self.assertEqual(audit.totals(self.ledger)["publisher_releases"],55)
        p["parent_database_sha256"]="f"*64
        with self.assertRaises(ValueError):audit.totals(self.ledger)
