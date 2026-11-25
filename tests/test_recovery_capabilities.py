import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from recovery_capabilities import exact_document
from restore_snapshot import recover,LOCK

class RecoveryCapabilityTests(unittest.TestCase):
    def test_archived_document_reused_no_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/"archive";stage=root/"stage";archive.mkdir();stage.mkdir()
            p=archive/"dict";p.write_bytes(b"abc")
            h=hashlib.sha256(b"abc").hexdigest();download=Mock()
            self.assertEqual(exact_document(archive,stage,"dict",h,3,download,False),p)
            download.assert_not_called()
            p.write_bytes(b"xyz")
            with self.assertRaises(ValueError):exact_document(archive,stage,"dict",h,3,download,True)
            download.assert_not_called()
    def test_missing_dictionary_fails_before_output_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/"output"
            with self.assertRaises(ValueError):recover(LOCK,root,out,False,True)
            self.assertFalse(out.exists())
    def test_no_unpinned_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);download=Mock()
            with self.assertRaises(ValueError):exact_document(None,root,"dict","0"*64,3,download,False)
            download.assert_not_called()
    def test_download_must_match_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def download(p):p.write_bytes(b"xyz")
            with self.assertRaises(ValueError):exact_document(None,root,"dict",hashlib.sha256(b"abc").hexdigest(),3,download,True)
