"""Exercise the actual loopback qualification against a controlled fixture."""
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import facilitysignal as fs
import private_iqies_service_research as research
from build_combined import sha
from iqies_additional_services import DDL
from scripts import qualify_iqies_private_http as q


class NationalPrivateHTTPTests(unittest.TestCase):
    def test_full_http_harness_and_database_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.sqlite3"
            fs.init(path)
            with closing(fs.connect(path)) as db:
                db.executescript(DDL)
                db.execute("INSERT INTO certification_releases VALUES(?,?,?,?,?,?,?,?,?)",
                           ("iqies","iqies","Q3","api","url","source",5,"date","{}"))
                db.execute("INSERT INTO iqies_additional_service_release VALUES(1,?,?,?,?)",
                           ("source",research.DICT_SHA,"Q3",5))
                for n in range(1,6):
                    db.execute("INSERT INTO certification_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               ("iqies",n,"hash",f"{n:06}","Fixture "+str(n),"Street","Town","NY","00001","8","","","",""))
                db.executemany("INSERT INTO iqies_additional_service_observations VALUES(?,?,?,?,?)",
                               [("iqies",n,"ft_srgry_sw","ASC",state) for n,state in enumerate(
                                   ("reported_yes","reported_no","not_available","reported_yes","reported_no"),1)])
                db.commit()
            expected = {"database_sha256": sha(path),"source_sha256":"source",
                        "dictionary_sha256":research.DICT_SHA,"source_period":"Q3","verified_source_rows":5,
                        "field_states":{"ft_srgry_sw":{"reported_yes":2,"reported_no":2,"not_available":1}}}
            with patch.object(research,"pinned",return_value=expected), patch.object(research,"verify_database"):
                result = q.qualify_http(path, expected)
            self.assertEqual(result["checks"],{"field_state":3,"all_states":1,"pagination":1,"geography":1,
                            "literal_search":4,"invalid_requests":7,"default_denial":1})
            self.assertEqual(result["successful_requests"],10)
            self.assertEqual(result["response_rows_published"],0)
            self.assertEqual(sha(path),expected["database_sha256"])

    def test_reject_wrong_hash_before_starting_server(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture"
            path.write_bytes(b"fixture")
            with patch.object(q,"server") as server:
                with self.assertRaisesRegex(ValueError,"database pin mismatch"):
                    q.qualify_http(path,{"database_sha256":"wrong"})
                server.assert_not_called()
