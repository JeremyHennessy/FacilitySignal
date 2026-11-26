import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from private_snapshot_archive import DB,AUDIT,backup,restore,sha

@unittest.skipUnless(os.name=="posix","private POSIX storage only")
class ArchiveTests(unittest.TestCase):
    def fixture(self,root):
        src=root/"source";src.mkdir(mode=0o700)
        with sqlite3.connect(src/DB) as db:
            db.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY)")
            db.execute("INSERT INTO sample VALUES(1)")
        db.close()
        (src/AUDIT).write_text(json.dumps({"database_sha256":sha(src/DB),"database_bytes":(src/DB).stat().st_size}))
        return src,sha(src/AUDIT)
    def test_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src,pin=self.fixture(root);archive=root/"snapshot.zip";out=root/"restored"
            result=backup(src,archive,pin)
            self.assertEqual(archive.stat().st_mode&0o777,0o600)
            restore(archive,out,pin,result["archive_sha256"])
            self.assertEqual(sha(out/DB),sha(src/DB))
            self.assertEqual(sha(out/AUDIT),pin)
            with self.assertRaises(ValueError):backup(src,archive,pin)
            with self.assertRaises(ValueError):restore(archive,out,pin,result["archive_sha256"])
            self.assertEqual(sha(out/DB),sha(src/DB))
    def test_wrong_pin_sidecar_and_tampered_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src,pin=self.fixture(root);archive=root/"snapshot.zip"
            with self.assertRaises(ValueError):backup(src,archive,"0"*64)
            (src/(DB+"-wal")).touch()
            with self.assertRaises(ValueError):backup(src,archive,pin)
            (src/(DB+"-wal")).unlink()
            with (src/DB).open("ab") as f:f.write(b"x")
            with self.assertRaises(ValueError):backup(src,archive,pin)
            self.assertFalse(archive.exists())
    def test_archive_drift_and_unexpected_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src,pin=self.fixture(root);archive=root/"snapshot.zip";out=root/"restored"
            result=backup(src,archive,pin)
            with zipfile.ZipFile(archive,"a") as z:z.writestr("../unexpected","x")
            with self.assertRaises(ValueError):restore(archive,out,pin,result["archive_sha256"])
            with self.assertRaises(ValueError):restore(archive,out,pin,sha(archive))
            self.assertFalse(out.exists());self.assertFalse((root/"unexpected").exists())
    def test_symlink_and_nonprivate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src,pin=self.fixture(root);archive=root/"snapshot.zip"
            link=root/"link";link.symlink_to(src,target_is_directory=True)
            with self.assertRaises(ValueError):backup(link,archive,pin)
            src.chmod(0o755)
            with self.assertRaises(ValueError):backup(src,archive,pin)
            self.assertFalse(archive.exists())
