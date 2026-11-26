import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(name):return json.loads((ROOT/"research"/name).read_text())
class AzureStorageCheckpointTests(unittest.TestCase):
    def test_private_retention_is_current_not_historical_inflation(self):
        c=read("azure_storage_checkpoint_20261126.json");l=read("coverage_status.json")
        s=l["current_private_storage"];n=c["national"]["receipt"];e=c["extension"]["receipt"]
        self.assertTrue(s["verified"]);self.assertEqual(n["source_records"],1904060)
        self.assertEqual(e["source_records"],865809)
        self.assertEqual(s["total_archived_source_records"],2769869)
        self.assertEqual(s["distinct_source_release_count"],35)
        self.assertEqual(s["total_payload_bytes"],n["total_bytes"]+e["total_bytes"])
        self.assertEqual(s["archive_payload_files"],66)
        self.assertTrue(n["independent_sqlite_restore_verified"])
        self.assertTrue(e["pointer_verified"]);self.assertTrue(e["source_lineage_verified"])
        self.assertEqual(e["base_release"],n["release"])
        self.assertEqual(n["payload_reuploads"]+e["payload_reuploads"],0)
        self.assertEqual(e["application_pack_parity"],{"byte_parity":True,"bytes":12589349,"file_count":15,"pages_paths_unchanged":True})
        self.assertEqual(sum(c["extension"]["source_rows"].values()),865809)
        self.assertEqual(len(c["extension"]["source_rows"]),16)
        for sid,count in c["extension"]["source_rows"].items():
            row=next(x for x in l["sources"] if x["id"]==sid)
            self.assertEqual(row["retained_database_rows"],0)
            self.assertEqual(row["current_private_archive"]["verified_rows"],count)
            self.assertFalse(row["current_private_archive"]["public_row_level_promotion"])
        self.assertEqual(read("snapshot_release_20261125.json")["source_records_total"],1904060)
        self.assertEqual(s["hrsa_screened_rows_archived"]+s["nppes_rows_archived"]+s["hcris_rows_archived"],0)
        self.assertFalse(s["raw_sources_archived"]);self.assertFalse(s["public_promotion"])
    def test_weekly_first_live_run(self):
        c=read("azure_storage_checkpoint_20261126.json");l=read("coverage_status.json");w=c["weekly_refresh"]
        self.assertEqual(w["schedule_utc"],"17 11 * * 1")
        self.assertIn("cron: '17 11 * * 1'",(ROOT/w["workflow"]).read_text())
        self.assertEqual(w["audit"]["failed_checks"],[])
        self.assertFalse(w["audit"]["public_promotion"])
        self.assertEqual(l["weekly_refresh_checkpoint"]["initial_live_run"],45848539102)
        self.assertTrue(all(v["state"]=="unchanged" for v in w["audit"]["sources"].values() if "state" in v))
        self.assertEqual(len(w["audit"]["sources"]["registry_and_ownership"]),9)
        self.assertEqual(len(w["audit"]["sources"]["nppes"]["weeks"]),3)
        self.assertEqual(c["live_pages"]["automated_screens_captured"],120)
