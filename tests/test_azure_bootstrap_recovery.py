import hashlib,io,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import azure_national_archive as a
from scripts import recover_azure_bootstrap as r
from scripts.azure_inventory import etag_relation,verify_inventory
from tests.test_azure_national_archive import Store

class MixedETagStore(Store):
    def list(self,p):
        for item in super().list(p):
            if item["etag"].startswith('"0x'):item["etag"]=item["etag"][1:-1]
            yield item

def seed(s):
    data={"snapshot/facilitysignal.sqlite3":b"synthetic db","snapshot/recovery-audit.json":b"synthetic audit","web/test.json":b"{}"}
    records=[a.bytes_record(path,d) for path,d in data.items()]
    for i,(path,d) in enumerate(data.items()):
        s.data[r.PAYLOAD+"/"+path]=(d,'"0x'+str(i+1)+'"')
    return records

class AzureRecoveryTests(unittest.TestCase):
    def test_etag_only_quoted_equivalence(self):
        self.assertEqual(etag_relation("0xAB",'"0xAB"'),"quote_only")
        self.assertEqual(etag_relation('"0xAB"','"0xAB"'),"exact")
        for x in ("0xab","0xAC",'W/"0xAB"'," 0xAB",'""0xAB""',None):
            self.assertEqual(etag_relation(x,'"0xAB"'),"different")
    def test_inventory_still_requires_exact_head_and_size(self):
        s=MixedETagStore();records=seed(s)
        etags={r.PAYLOAD+"/"+x["path"]:s.head(r.PAYLOAD+"/"+x["path"])["etag"] for x in records}
        self.assertEqual(verify_inventory(s,r.PAYLOAD,records,etags)["list_head_etag_relations"]["quote_only"],3)
        name=next(iter(etags));d,e=s.data[name];s.data[name]=(d,'"0xFF"')
        with self.assertRaises(ValueError):verify_inventory(s,r.PAYLOAD,records,etags)
    def test_recover_create_only_no_reupload(self):
        s=MixedETagStore();records=seed(s);before=dict(s.data)
        pin={"run":45845760984,"commit":r.ORIGINAL_COMMIT}
        audit={"source_records_total":1904060,"database_bytes":12,"database_sha256":"a"*64,"source_lock_sha256":"b"*64}
        with tempfile.TemporaryDirectory() as d,patch.object(r,"reconcile_database",return_value=audit):
            out=r.recover(s,pin,records,Path(d),"bootstrap-999-1","c"*40)
            self.assertEqual(out["payload_reuploads"],0)
            self.assertTrue(s.exists(a.POINTER));self.assertTrue(s.exists(r.COMPLETE))
            self.assertTrue(all(s.data[k]==v for k,v in before.items()))
            with self.assertRaises(ValueError):r.recover(s,pin,records,Path(d),"bootstrap-999-2","c"*40)
    def test_corrupt_upload_not_promoted(self):
        s=MixedETagStore();records=seed(s);s.corrupt=True
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):r.recover(s,{"run":45845760984,"commit":r.ORIGINAL_COMMIT},records,Path(d),"bootstrap-999-1","c"*40)
            self.assertFalse(s.exists(a.POINTER));self.assertFalse(s.exists(r.COMPLETE))
    def test_pinned_reconstruction_and_expected_git_tree(self):
        pin=r.load_pin()
        # The recovery workflow uses full history; ordinary shallow CI need
        # not download the original commit just to run synthetic tests.
        if subprocess.run(["git","cat-file","-e",pin["commit"]+"^{commit}"],cwd=r.ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            self.skipTest("Original commit absent in shallow checkout; full-history recovery gate covers this")
        records=r.expected_records(pin)
        self.assertEqual(next(x for x in records if x["path"]=="snapshot/facilitysignal.sqlite3")["sha256"],pin["reconstruction_audit"]["database_sha256"])
        self.assertNotIn("research/azure_bootstrap_recovery_pin_20261126.json",{x["path"] for x in records})
