import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
from unittest.mock import patch

import facilitysignal as fs
import private_iqies_service_research as q
from iqies_additional_services import DDL, RULES
from build_combined import sha


class PrivateServiceSearchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "fixture.sqlite3"
        fs.init(self.path)
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.executescript(DDL)
        self.db.execute("INSERT INTO certification_releases VALUES(?,?,?,?,?,?,?,?,?)",
                        ("iqies","iqies","Q3","api","url","source",3,"date","{}"))
        self.db.execute("INSERT INTO iqies_additional_service_release VALUES(1,?,?,?,?)",
                        ("source",q.DICT_SHA,"Q3",3))
        for n,state in ((1,"NY"),(2,"NY"),(3,"CA")):
            self.db.execute("INSERT INTO certification_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            ("iqies",n,"hash",f"{n:06}","Fixture "+str(n),"Street","Town",state,"00001","8","","","",""))
        self.db.executemany("INSERT INTO iqies_additional_service_observations VALUES(?,?,?,?,?)",
                            [("iqies",1,"ft_srgry_sw","ASC","reported_yes"),
                             ("iqies",2,"ft_srgry_sw","ASC","reported_no"),
                             ("iqies",3,"ft_srgry_sw","ASC","not_available")])
        self.db.commit()
        self.expected = {"source_sha256":"source","source_period":"Q3","verified_source_rows":3,
                         "field_states":{"ft_srgry_sw":{"reported_yes":1,"reported_no":1,"not_available":1}}}
        p=patch.object(q,"pinned",return_value=self.expected)
        p.start();self.addCleanup(p.stop)

    def test_source_state_filters_and_pagination(self):
        p={"field":"ft_srgry_sw"}
        self.assertEqual(q.search(self.db,p)["total"],3)
        self.assertEqual(q.search(self.db,{**p,"state":"NY","value_state":"reported_yes"})["total"],1)
        self.assertEqual(q.search(self.db,{**p,"value_state":"not_available"})["rows"][0]["row_number"],3)
        self.assertEqual(q.search(self.db,{**p,"q":"%"} )["total"],0)
        self.assertEqual(len(q.search(self.db,{**p,"limit":"1","page":"2"})["rows"]),1)
        for invalid in ({"field":"bad"},{"field":"ft_srgry_sw","min":"1"},{"field":"ft_srgry_sw","value_state":"reported_count"},{"field":"ft_srgry_sw","limit":"101"}):
            with self.assertRaises(ValueError):q.search(self.db,invalid)

    def test_missing_and_mismatched_data_fail_closed(self):
        p={"field":"ft_srgry_sw"}
        self.db.execute("UPDATE iqies_additional_service_release SET dictionary_sha256='wrong'")
        x=q.search(self.db,p);self.assertEqual(x["status"],"lineage_mismatch");self.assertIsNone(x["total"])
        self.db.execute("UPDATE iqies_additional_service_release SET dictionary_sha256=?",(q.DICT_SHA,))
        self.db.execute("DELETE FROM iqies_additional_service_observations WHERE row_number=1")
        x=q.search(self.db,p);self.assertEqual(x["status"],"domain_mismatch");self.assertEqual(x["rows"],[])
        self.db.execute("DROP TABLE iqies_additional_service_observations")
        self.assertEqual(q.search(self.db,p)["status"],"not_loaded")

    def test_loopback_http_opt_in_and_default_denial(self):
        def request(enabled):
            with patch.object(q,"verify_database") as verified:
                handler=fs.handler(self.path,private_service_extension=enabled)
                self.assertEqual(verified.called,enabled)
                with fs.ThreadingHTTPServer(("127.0.0.1",0),handler) as server:
                    thread=threading.Thread(target=server.serve_forever,daemon=True)
                    thread.start()
                    try:
                        url=f"http://127.0.0.1:{server.server_port}/api/iqies-additional-services?field=ft_srgry_sw&value_state=reported_yes"
                        if enabled:
                            with urlopen(url,timeout=5) as res:
                                self.assertEqual(res.headers["Cache-Control"],"no-store")
                                self.assertEqual(json.load(res)["total"],1)
                        else:
                            with self.assertRaises(HTTPError) as exc:urlopen(url,timeout=5)
                            self.assertEqual(exc.exception.code,404)
                    finally:
                        server.shutdown();thread.join(timeout=5)
        before=sha(self.path)
        request(False);request(True)
        self.assertEqual(sha(self.path),before)

    def test_actual_receipt_and_field_labels(self):
        proof=json.loads(q.ROUNDTRIP.read_text())["receipt"]
        self.assertEqual(proof["observations"],93913)
        self.assertEqual(proof["restored_database_sha256"],proof["qualified_candidate_sha256"])
        self.assertEqual(proof["baseline_tables_preserved"],21)
        self.assertTrue(proof["extension_tables_exact_bidirectional_parity"])
        self.assertFalse(proof["private_storage_written"])
        self.assertFalse(proof["storage_cost_verified"])
        self.assertEqual(set(q.LABELS),set(RULES))
        with patch.object(q,"pinned",return_value=json.loads(q.NATIONAL.read_text())["receipt"]):
            with self.assertRaisesRegex(ValueError,"checksum mismatch"):q.verify_database(self.path)
