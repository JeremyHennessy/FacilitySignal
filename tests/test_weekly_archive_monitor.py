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
