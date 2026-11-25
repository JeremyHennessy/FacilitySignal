import csv
import hashlib
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
import facilitysignal as fs
import collect_registry as cr

class RegistryTests(unittest.TestCase):
    def test_version_specific_catalog(self):
        d={"dataset":[{"title":cr.TITLES["qies"],"accessLevel":"public","distribution":[{"format":"API","description":"latest","temporal":"2026-Q3","accessURL":cr.ROOT+"/latest"},{"format":"API","temporal":"2026-Q3","accessURL":cr.ROOT+"/"+cr.PINNED["qies"]},{"format":"CSV","temporal":"2026-Q3","downloadURL":cr.ROOT+"/release.csv"}]}]}
        result=cr.choose(d,"qies")
        self.assertIn(cr.PINNED["qies"],result["api"])
        self.assertEqual(result["url"],cr.ROOT+"/release.csv")
        d["dataset"][0]["distribution"].append(dict(d["dataset"][0]["distribution"][2]))
        with self.assertRaises(ValueError): cr.choose(d,"qies")
    def test_import_and_search_separate_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/"data.sqlite3";p=Path(temp)/"data.csv";fs.init(db)
            with p.open("w",newline="") as f:
                w=csv.writer(f);w.writerow(["PRVDR_NUM","FAC_NAME","ST_ADR","CITY_NAME","STATE_CD","ZIP_CD","PRVDR_CTGRY_CD","TRMNTN_EXPRTN_DT"])
                w.writerow(["010001","Test provider","1 Fixture Road","Fixture","AL","01234","01","2025-01-01"])
                w.writerow(["010001","Historical provider","1 Fixture Road","Fixture","AL","01234","01","2020-01-01"])
            meta={"registry":"qies","title":"fixture","period":"2026-Q3","api":cr.ROOT+"/api","url":cr.ROOT+"/csv","zipped":False}
            with self.assertRaises(ValueError):
                cr.import_registry(db,meta,p,hashlib.sha256(p.read_bytes()).hexdigest(),3)
            with closing(fs.connect(db)) as conn: self.assertEqual(fs.registry_search(conn,{})["total"],0)
            result=cr.import_registry(db,meta,p,hashlib.sha256(p.read_bytes()).hexdigest(),2)
            self.assertEqual(result["repeated_id_rows"],1)
            with closing(fs.connect(db)) as conn:
                self.assertEqual(fs.registry_search(conn,{"q":"010001","registry":"qies"})["total"],2)
                self.assertIsNone(fs.overview(conn)["facility_records"])
                self.assertIn("Historical provider",fs.render_certifications(conn,{}))
    def test_missing_header_rejected(self):
        with self.assertRaises(ValueError): cr.mapping(["FAC_NAME","PRVDR_NUM"])

    def test_legacy_encoding_is_strict(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"legacy.csv"
            p.write_bytes(b"NAME\nTest\xa0Provider\n")
            self.assertEqual(cr.source_encoding(p,False),"cp1252")
            with cr.open_csv(p,False,"cp1252") as f:
                self.assertIn("\u00a0",f.read())
            p.write_bytes(b"NAME\nTest\x81Provider\n")
            with self.assertRaises(ValueError): cr.source_encoding(p,False)
