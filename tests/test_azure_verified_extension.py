import hashlib,io,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import azure_verified_extension as e
import azure_national_archive as a
from tests.test_azure_national_archive import Store

class ExtensionStore(Store):
    def create(self,n,s,size,kind):
        if n in self.data:raise ValueError("exists")
        d=s.read()
        if len(d)!=size:raise ValueError("size")
        self.counter+=1;etag=str(self.counter);self.data[n]=(d,etag)
        return etag

def seed(store):
    release="bootstrap-123-1";prefix=a.PREFIX+"/releases/"+release
    db=b"synthetic db";audit=b"synthetic audit"
    files=[a.bytes_record("snapshot/facilitysignal.sqlite3",db),a.bytes_record("snapshot/recovery-audit.json",audit)]
    rec={"format_version":1,"status":"COMPLETE","domain":"FACILITYSIGNAL_NATIONAL_ARCHIVE","release":release,"commit":"a"*40,"source_records":1904060,"sha256_readback":True,"exact_inventory":True,"payload_prefix":prefix+"/files","source_lock_sha256":a.sha(e.LOCK),"file_count":2,"total_bytes":len(db)+len(audit),"database_bytes":len(db),"database_sha256":hashlib.sha256(db).hexdigest(),"files":files}
    raw=a.encode(rec);name=prefix+"/complete.json"
    store.create(name,io.BytesIO(raw),len(raw),"application/json")
    p={"format_version":1,"domain":rec["domain"],"release":release,"commit":rec["commit"],"source_records":1904060,"receipt":name,"receipt_sha256":hashlib.sha256(raw).hexdigest()}
    raw=a.encode(p);store.create(a.POINTER,io.BytesIO(raw),len(raw),"application/json")
    return p

class AzureExtensionTests(unittest.TestCase):
    def test_path_and_write_boundary(self):
        e.extension_name(e.EXT_POINTER)
        e.extension_name(a.PREFIX+"/releases/extension-12-1/files/extension.sqlite3")
        for n in (a.POINTER,a.PREFIX+"/releases/bootstrap-12-1/files/test",a.PREFIX+"/releases/extension-12-1/files/../x","TowerSignal/a"):
            with self.assertRaises(ValueError):e.extension_name(n)
    def test_national_manifest_and_drift(self):
        s=ExtensionStore();seed(s);n=e.national_manifest(s)
        self.assertEqual(n["receipt"]["source_records"],1904060)
        e.unchanged(s,n)
        raw,_=s.data[a.POINTER];s.data[a.POINTER]=(raw,"changed")
        with self.assertRaises(ValueError):e.unchanged(s,n)
        s=ExtensionStore();seed(s);s.corrupt=True
        with self.assertRaises((ValueError,json.JSONDecodeError)):e.national_manifest(s)
    def test_integrity_of_extension_schema(self):
        with sqlite3.connect(":memory:") as db:
            e.init_extension(db)
            with self.assertRaises(sqlite3.IntegrityError):db.execute("INSERT INTO qcor_provider_rows VALUES('FS-025',1,'a','b','c','memo')")
            db.rollback()
            for sid in ("FS-025","FS-028"):
                db.execute("INSERT INTO extension_sources VALUES(?,?,?,?,?,?)",(sid,"qcor_provider_rows","a"*64,1,1,1))
                db.execute("INSERT INTO qcor_provider_rows VALUES(?,?,?,?,?,?)",(sid,1,"same","same","2024-01-01","memo"))
            self.assertEqual(db.execute("SELECT count(*) FROM qcor_provider_rows").fetchone()[0],2)
    def test_create_only_extension_pointer(self):
        s=ExtensionStore();seed(s);n=e.national_manifest(s);old=s.data[a.POINTER]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);db=root/"extension.sqlite3";db.write_bytes(b"synthetic extension")
            audit={"database_sha256":a.sha(db),"database_bytes":db.stat().st_size,"base_database_sha256":n["receipt"]["database_sha256"],"source_records":e.EXPECTED_ROWS,"scope":"synthetic"}
            receipt=e.publish(s,"extension-123-1","b"*40,n,db,audit,root)
            self.assertTrue(receipt["sha256_readback"])
            self.assertTrue(s.exists(e.EXT_POINTER));self.assertEqual(s.data[a.POINTER],old)
            with self.assertRaises(ValueError):e.publish(s,"extension-123-2","b"*40,n,db,audit,root)
    def test_readback_mismatch(self):
        s=ExtensionStore();data=b"synthetic";name=a.PREFIX+"/releases/bootstrap-123-1/files/snapshot/facilitysignal.sqlite3"
        s.create(name,io.BytesIO(data),len(data),"application/octet-stream")
        pin=a.bytes_record("snapshot/facilitysignal.sqlite3",data)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);e.fetch_verified(s,name,pin,root/"good")
            s.corrupt=True
            with self.assertRaises(ValueError):e.fetch_verified(s,name,pin,root/"bad")
