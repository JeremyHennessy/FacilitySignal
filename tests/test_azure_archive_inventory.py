import copy,hashlib,json,unittest
from scripts import audit_azure_archive_inventory as audit

class ArchiveInventoryTests(unittest.TestCase):
    def setUp(self): self.ledger=json.loads(audit.LEDGER.read_text())
    def test_counts_and_grain(self):
        t=audit.totals(self.ledger)
        self.assertEqual(t["publisher_releases"],56)
        self.assertEqual(t["source_observations"],117850722)
        self.assertEqual(t["derived_candidate_observations"],23520)
        self.assertEqual(t["payload_files"],214)
        self.assertEqual(t["derived_enrollment_corroboration_rows"],40709)
        self.assertEqual(t["derived_institutional_observations"],101534)
        self.assertEqual(t["repository_data_evidence_files"],73)
        self.assertEqual(t["repository_supplemental_data_files"],13)
        self.assertEqual(t["supplemental_numeric_archives"],41)
        self.assertEqual(t["supplemental_numeric_observations"],107619587)
        self.assertEqual(t["aggregate_evidence_releases"],8)
        self.assertEqual(t["aggregate_source_rows_screened"],40787611)
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
        self.assertEqual(audit.totals(self.ledger)["publisher_releases"],self.ledger["totals"]["publisher_releases"])
        p["parent_database_sha256"]="f"*64
        with self.assertRaises(ValueError):audit.totals(self.ledger)

    def test_supplements_cannot_inflate_publisher_count(self):
        for kind in ("institutional_fields","evidence_bundle"):
            altered=copy.deepcopy(self.ledger)
            next(x for x in altered["receipts"] if x["kind"]==kind)["kind"]="publisher"
            with self.assertRaises(ValueError):audit.totals(altered)

    def test_evidence_receipt_path_and_manifest_reconciliation(self):
        pin=copy.deepcopy(next(x for x in self.ledger["receipts"] if x["kind"]=="evidence_bundle"))
        manifest=[{"path":"research/old.json","bytes":3,"sha256":"a"*64},{"path":"web/hcris-capacity/hospital.json","bytes":5,"sha256":"b"*64}]
        national={"receipt_sha256":pin["base_receipt_sha256"],"pointer":{"release":"bootstrap-1-1"},"files":{manifest[0]["path"]:manifest[0]}}
        inputs={"base_receipt_sha256":national["receipt_sha256"],"policy_version":1,"tracked_data_files":manifest}
        pin.update(source_sha256=hashlib.sha256(audit.a.encode(inputs)).hexdigest(),tracked_data_file_count=2,supplemental_file_count=1)
        receipt={"status":"COMPLETE","domain":"FACILITYSIGNAL_PRIVATE_SOURCE","format_version":1,"projector_version":1,"key":pin["key"],"source_sha256":pin["source_sha256"],"payload_prefix":audit.src.prefix_for(pin["key"],pin["source_sha256"])+"/files","base_receipt_sha256":pin["base_receipt_sha256"],"base_release":"bootstrap-1-1","files":pin["files"],"total_bytes":sum(f["bytes"] for f in pin["files"]),"sha256_readback":True,"public_promotion":False,"publisher":{"kind":"repository_data_evidence_snapshot","inputs":inputs,"sha256":pin["source_sha256"]},"summary":{"complete_manifest":manifest,"new_publisher_release":False,"tracked_data_file_count":2,"supplemental_file_count":1,"base_file_count":1,"supplemental_paths":[manifest[1]["path"]],"supplemental_data_bytes":5,"tracked_data_bytes":8}}
        audit.source_matches(receipt,pin,national)
        manifest[1]["path"]="web/../secret.json"
        pin["source_sha256"]=hashlib.sha256(audit.a.encode(inputs)).hexdigest()
        receipt.update(source_sha256=pin["source_sha256"],payload_prefix=audit.src.prefix_for(pin["key"],pin["source_sha256"])+"/files")
        with self.assertRaisesRegex(ValueError,"evidence manifest file"):audit.source_matches(receipt,pin,national)

    def test_enrollment_corroboration_receipt_and_lineage(self):
        p=next(x for x in self.ledger["receipts"] if x["kind"]=="enrollment_corroboration")
        r=json.loads((audit.ROOT/"research/pecos_ppef_corroboration_qualification_20261126.json").read_text())["receipt"]
        national={"receipt_sha256":p["base_receipt_sha256"],"receipt":{"database_sha256":p["inputs"]["national_database_sha256"]},"pointer":{"release":r["base_release"]}}
        audit.source_matches(r,p,national)
        bad=copy.deepcopy(r);bad["summary"]["by_family"]["hospital-enrollment"]["exact_all_keys"]+=1
        with self.assertRaises(ValueError):audit.source_matches(bad,p,national)
        altered=copy.deepcopy(self.ledger);next(x for x in altered["receipts"] if x["kind"]=="enrollment_corroboration")["kind"]="publisher"
        with self.assertRaises(ValueError):audit.totals(altered)
        altered=copy.deepcopy(self.ledger);next(x for x in altered["receipts"] if x["kind"]=="enrollment_corroboration")["inputs"]["archives"]["ppef-type2-enrollment"]["database_sha256"]="a"*64
        with self.assertRaises(ValueError):audit.totals(altered)
