import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from restore_snapshot import LOCK,load_lock,verify_raw,materialize,recover

class RecoveryTests(unittest.TestCase):
    def test_release_lock(self):
        lock=load_lock(LOCK)
        self.assertEqual(len(lock["sources"]),19)
        self.assertEqual(lock["source_records_total"],1904060)
        self.assertTrue(all(s["download_url"] for s in lock["sources"]))
        self.assertEqual(sum(s["excluded_rows"] for s in lock["sources"]),326781)
    def test_exact_bytes_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"example.csv";p.write_bytes(b"abc")
            item={"key":"example","file":"example.csv","bytes":3,"sha256":hashlib.sha256(b"abc").hexdigest()}
            self.assertEqual(materialize(item,Path(tmp),Path(tmp),False),p)
            p.write_bytes(b"xyz")
            with self.assertRaises(ValueError): verify_raw(p,item)
            with self.assertRaises(ValueError): materialize(item,Path(tmp),Path(tmp),True)
            p.unlink()
            with self.assertRaises(ValueError): materialize(item,Path(tmp),Path(tmp),False)
    def test_lock_drift_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"lock.json";lock=load_lock(LOCK)
            lock["sources"][0]["stored_rows"]+=1
            p.write_text(json.dumps(lock))
            with self.assertRaises(ValueError): load_lock(p)
    def test_failed_recovery_does_not_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/"output"
            with self.assertRaises(ValueError): recover(LOCK,root,out,False)
            self.assertFalse(out.exists())
            out.mkdir();marker=out/"preserve";marker.write_text("known good")
            with self.assertRaises(ValueError): recover(LOCK,root,out,False)
            self.assertEqual(marker.read_text(),"known good")
