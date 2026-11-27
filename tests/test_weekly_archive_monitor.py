import unittest
from scripts.weekly_archive_monitor import compare_metadata
class WeeklyArchiveMonitorTests(unittest.TestCase):
    def test_change_and_unknown(self):
        self.assertEqual(compare_metadata({"etag":"a"},{"etag":"a"},("etag",)),"metadata_unchanged")
        self.assertEqual(compare_metadata({"etag":"a"},{"etag":"b"},("etag",)),"new_version_review")
        self.assertEqual(compare_metadata({"etag":"a"},{},("etag",)),"metadata_review")


class NursingOwnershipMonitorTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        import json
        from scripts import weekly_archive_monitor as monitor
        self.monitor=monitor
        self.receipt=json.loads((Path(__file__).resolve().parents[1]/"research/fs039_nursing_ownership_archive_receipt_20261126.json").read_text())["receipt"]
        self.old=self.receipt["publisher"]
        self.meta={k:self.old[k] for k in ("id","released","modified","url")}

    def test_unchanged_uses_full_publisher_count_not_projected_rows(self):
        from unittest.mock import patch
        with patch.object(self.monitor.cms,"metadata",return_value=self.meta) as meta, patch.object(self.monitor.cms,"count",return_value=252468) as count, patch.object(self.monitor.cms,"download") as download:
            result=self.monitor.nursing_ownership_metadata(self.receipt)
            meta.assert_called_once_with("y2hd-n93e")
            count.assert_called_once_with("y2hd-n93e")
            download.assert_not_called()
        self.assertEqual(result["state"],"metadata_unchanged")
        self.assertEqual(result["api_count"],252468)
        self.assertEqual(result["retained_organization_rows"],71270)

    def test_changed_and_missing_metadata_remain_review_only(self):
        from unittest.mock import patch
        for meta,count,expected in [
            (self.meta,252469,"new_version_review"),
            ({**self.meta,"modified":"2026-11-01"},252468,"new_version_review"),
            ({**self.meta,"url":self.meta["url"]+"?revision=1"},252468,"new_version_review"),
            ({**self.meta,"modified":None},252468,"metadata_review")]:
            with self.subTest(expected=expected), patch.object(self.monitor.cms,"metadata",return_value=meta), patch.object(self.monitor.cms,"count",return_value=count), patch.object(self.monitor.cms,"download") as download:
                self.assertEqual(self.monitor.nursing_ownership_metadata(self.receipt)["state"],expected)
                download.assert_not_called()

    def test_reject_wrong_identity(self):
        from unittest.mock import patch
        with patch.object(self.monitor.cms,"metadata",return_value={**self.meta,"id":"wrong"}), patch.object(self.monitor.cms,"count") as count:
            with self.assertRaisesRegex(ValueError,"identity changed"):
                self.monitor.nursing_ownership_metadata(self.receipt)
            count.assert_not_called()

    def test_monitor_routes_exact_archive_key(self):
        from unittest.mock import patch,Mock
        pin={"key":"cms-nursing-ownership-organizations","source_sha256":self.receipt["source_sha256"],"kind":"source"}
        store=Mock()
        with patch.object(self.monitor,"LEDGER") as ledger, patch.object(self.monitor,"read_small",return_value=(self.receipt,None,None)), patch.object(self.monitor,"source_matches") as verify, patch.object(self.monitor.cms,"metadata",return_value=self.meta), patch.object(self.monitor.cms,"count",return_value=252468):
            import json
            ledger.read_text.return_value=json.dumps({"receipts":[pin]})
            result=self.monitor.monitor(store,{})
            verify.assert_called_once_with(self.receipt,pin,{})
        self.assertEqual(next(iter(result.values()))["state"],"metadata_unchanged")
        store.create.assert_not_called()


class MetadataChangeEvidenceTests(unittest.TestCase):
    def test_changed_etag_only_does_not_claim_byte_change(self):
        from scripts.weekly_archive_monitor import metadata_change_evidence
        fields=("etag","last_modified","bytes")
        result=metadata_change_evidence(
            {"etag":"old","last_modified":"same","bytes":10},
            {"etag":"new","last_modified":"same","bytes":10},fields)
        self.assertEqual(result["state"],"new_version_review")
        self.assertEqual(result["changed_fields"],["etag"])
        self.assertEqual(result["equal_fields"],["last_modified","bytes"])
        self.assertFalse(result["byte_identity_verified"])
        self.assertNotIn('"new"',__import__("json").dumps(result))

    def test_missing_newly_available_and_equal_are_distinct(self):
        from scripts.weekly_archive_monitor import metadata_change_evidence
        result=metadata_change_evidence({"etag":"old","bytes":10},{"last_modified":"now"},
            ("etag","last_modified","bytes","other"))
        self.assertEqual(result["state"],"metadata_review")
        self.assertEqual(result["missing_current_fields"],["etag","bytes"])
        self.assertEqual(result["newly_available_fields"],["last_modified"])
        self.assertEqual(result["unavailable_in_both"],["other"])
        self.assertEqual(result["changed_fields"],[])

    def test_minnesota_and_osha_route_evidence_without_download(self):
        import json
        from unittest.mock import Mock, patch
        from scripts import weekly_archive_monitor as monitor
        from scripts import archive_state_equipment_directory as mn
        from scripts import archive_osha_enforcement_coverage as osha
        cases=[("mn-boiler-aggregate",{"url":"fixture","etag":"old","bytes":10}),
               ("osha-enforcement-healthcare-aggregate",{"sources":{
                   "inspection":{"etag":"old","bytes":10},
                   "violation":{"etag":"old","bytes":10}}})]
        for key,publisher in cases:
            with self.subTest(key=key):
                pin={"key":key,"source_sha256":"a"*64,"kind":"source"}
                store=Mock()
                with patch.object(monitor,"LEDGER") as ledger, patch.object(monitor,"read_small",return_value=({"publisher":publisher},None,None)), patch.object(monitor,"source_matches"), patch.object(mn,"head",return_value={"etag":"new","bytes":10}), patch.object(osha,"head",side_effect=lambda k:{"etag":"new" if k=="inspection" else "old","bytes":10}), patch.object(mn,"download") as md, patch.object(osha,"download") as od:
                    ledger.read_text.return_value=json.dumps({"receipts":[pin]})
                    out=next(iter(monitor.monitor(store,{}).values()))
                    md.assert_not_called()
                    od.assert_not_called()
                self.assertEqual(out["state"],"new_version_review")
                if key.startswith("mn-"):
                    self.assertEqual(out["changed_fields"],["etag"])
                else:
                    self.assertEqual(out["components"],{"inspection":"new_version_review","violation":"metadata_unchanged"})
                    self.assertEqual(out["component_metadata_evidence"]["inspection"]["changed_fields"],["etag"])
                    self.assertEqual(out["component_metadata_evidence"]["violation"]["changed_fields"],[])
                store.create.assert_not_called()
