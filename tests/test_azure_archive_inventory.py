import copy,json,unittest
from scripts import audit_azure_archive_inventory as audit

class ArchiveInventoryTests(unittest.TestCase):
    def setUp(self): self.ledger=json.loads(audit.LEDGER.read_text())
    def test_counts_and_grain(self):
        t=audit.totals(self.ledger)
        self.assertEqual(t["publisher_releases"],45)
        self.assertEqual(t["source_observations"],9639767)
        self.assertEqual(t["derived_candidate_observations"],23520)
        self.assertEqual(t["payload_files"],88)
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
