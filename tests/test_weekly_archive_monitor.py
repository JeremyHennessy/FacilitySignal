import unittest
from scripts.weekly_archive_monitor import compare_metadata
class WeeklyArchiveMonitorTests(unittest.TestCase):
    def test_change_and_unknown(self):
        self.assertEqual(compare_metadata({"etag":"a"},{"etag":"a"},("etag",)),"metadata_unchanged")
        self.assertEqual(compare_metadata({"etag":"a"},{"etag":"b"},("etag",)),"new_version_review")
        self.assertEqual(compare_metadata({"etag":"a"},{},("etag",)),"metadata_review")
