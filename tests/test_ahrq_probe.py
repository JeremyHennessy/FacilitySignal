import tempfile
import unittest
from pathlib import Path
from scripts.probe_ahrq import csv_probe,allowed,ROOT,SOURCES

class AhrqProbeTests(unittest.TestCase):
    def test_identifier_preservation_and_missing_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"x.csv"
            path.write_text("compendium_hospital_id,ccn,health_sys_id\nh1,001234,S1\nh2,001234,\nh3,,S2\n")
            stats,ids=csv_probe(path,"hospital",{"S1"})
            self.assertEqual(stats["rows"],3)
            self.assertEqual(stats["nonstandard_ccn"],0)
            self.assertEqual(stats["repeated_ccn_rows"],1)
            self.assertEqual(stats["missing_ccn"],1)
            self.assertEqual(stats["system_id_not_in_system_file"],1)
            self.assertEqual(ids,{"h1","h2","h3"})
    def test_reject_malformed_and_duplicate_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"x.csv"
            for source in ("health_sys_id,health_sys_id\n1,2\n","health_sys_id,name\n1\n"):
                path.write_text(source)
                with self.assertRaises(ValueError):csv_probe(path,"system")
    def test_download_allowlist(self):
        self.assertEqual(allowed(ROOT+SOURCES["system"]),ROOT+SOURCES["system"])
        with self.assertRaises(ValueError):allowed("https://example.org/file.csv")
