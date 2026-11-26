import io,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import azure_national_archive as a
from scripts import recover_azure_extension as r,azure_verified_extension as e
from tests.test_azure_verified_extension import ExtensionStore,seed
class QuotedStore(ExtensionStore):
    def create(self,n,s,size,kind):
        ret=super().create(n,s,size,kind)
        d,_=self.data[n];etag='"0x'+str(ret)+'"';self.data[n]=(d,etag);return etag
    def list(self,p):
        for x in super().list(p):
            if x["etag"].startswith('"0x'):x["etag"]=x["etag"][1:-1]
            yield x
class ExtensionRecoveryTests(unittest.TestCase):
    def test_both_inventory_checks_accept_quote_only(self):
        s=QuotedStore();seed(s);n=e.national_manifest(s)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);db=root/"extension.sqlite3";db.write_bytes(b"synthetic")
            audit={"database_sha256":a.sha(db),"database_bytes":db.stat().st_size,"base_database_sha256":n["receipt"]["database_sha256"],"source_records":e.EXPECTED_ROWS,"scope":"synthetic","application_pack_parity":{"byte_parity":True,"pages_paths_unchanged":True}}
            receipt=e.publish(s,"extension-123-1","b"*40,n,db,audit,root)
            self.assertEqual(receipt["inventory_etag_audit"]["list_head_etag_relations"]["quote_only"],3)
            self.assertTrue(s.exists(e.EXT_POINTER))
    def test_recovery_pin_and_receipt_scope(self):
        p=r.load_pin();self.assertEqual(sum(x["rows"] for x in p["source_log_results"].values()),e.EXPECTED_ROWS-e.FDA_ROWS)
        s=ExtensionStore();seed(s);n=e.national_manifest(s)
        n["pointer"]["release"]=p["base_release"];n["receipt"]["database_sha256"]=p["base_database_sha256"]
        files=[a.bytes_record(name,b"synthetic") for name in ("extension.sqlite3","extension-audit.json","expanded-source-lock.json")]
        rec={"format_version":1,"status":"COMPLETE","domain":e.EXT_DOMAIN,"release":r.RELEASE,"commit":r.COMMIT,"payload_prefix":r.PAYLOAD,"base_release":p["base_release"],"base_receipt_sha256":n["receipt_sha256"],"base_pointer_sha256":n["pointer_sha256"],"base_source_records":1904060,"source_records":e.EXPECTED_ROWS,"source_count":16,"sha256_readback":True,"exact_inventory":True,"application_pack_parity":p["app_parity"],"files":files,"file_count":3,"total_bytes":sum(x["bytes"] for x in files),"database_sha256":files[0]["sha256"],"database_bytes":files[0]["bytes"]}
        self.assertEqual(len(r.validate_receipt(rec,n,p)),3)
        with self.assertRaises(ValueError):r.validate_receipt({**rec,"base_receipt_sha256":"wrong"},n,p)
        with self.assertRaises(ValueError):r.validate_receipt({**rec,"source_records":0},n,p)
