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
                                payload=json.load(res)
                                self.assertEqual(payload["total"],1)
                                self.assertEqual(payload["indicator_kind"],"specialty_offered")
                                self.assertIn("not a negative response",payload["value_state_meanings"]["not_available"])
                        else:
                            with self.assertRaises(HTTPError) as exc:urlopen(url,timeout=5)
                            self.assertEqual(exc.exception.code,404)
                    finally:
                        server.shutdown();thread.join(timeout=5)
        before=sha(self.path)
        request(False);request(True)
        self.assertEqual(sha(self.path),before)

    def test_all_indicator_meanings_match_pinned_dictionary_scope(self):
        from iqies_additional_services import evidence
        reviewed, _ = evidence()
        for field, dictionary in reviewed.items():
            with self.subTest(field=field):
                context = q.indicator_context(field)
                self.assertEqual(q.LABELS[field], dictionary["label"])
                self.assertEqual(RULES[field][0], dictionary["applicability"])
                self.assertIn("not a negative response", context["value_state_meanings"]["not_available"])
                if field == "incntr_nctrnl_srvc_sw":
                    self.assertIn("begun", dictionary["definition"])
                    self.assertEqual(context["indicator_kind"], "commencement")
                    self.assertIn("begun", context["indicator_meaning"])
                elif field in ("sp_home_trng_sprt_hd_sw", "sp_home_trng_sprt_pd_sw"):
                    self.assertIn("continued", dictionary["definition"])
                    self.assertEqual(context["indicator_kind"], "continuation")
                    self.assertIn("continuing", context["indicator_meaning"])
                else:
                    self.assertEqual(context["indicator_kind"], "specialty_offered")
                if RULES[field][0] == "ESRD":
                    self.assertIn("does not establish that the service is absent", context["interpretation_limit"])

    def test_private_response_keeps_context_and_distinct_state(self):
        p = {"field": "ft_srgry_sw", "value_state": "not_available"}
        result = q.search(self.db, p)
        self.assertEqual(result["rows"][0]["value_state"], "not_available")
        self.assertEqual(result["indicator_kind"], "specialty_offered")
        self.assertIn("not a negative response", result["value_state_meanings"]["not_available"])
        for field, kind in (("incntr_nctrnl_srvc_sw","commencement"),
                            ("sp_home_trng_sprt_hd_sw","continuation"),
                            ("sp_home_trng_sprt_pd_sw","continuation")):
            with self.subTest(field=field):
                self.db.executemany("INSERT INTO iqies_additional_service_observations VALUES(?,?,?,?,?)",
                    [("iqies",n,field,"ESRD",state) for n,state in
                     ((1,"reported_yes"),(2,"reported_no"),(3,"not_available"))])
                self.expected["field_states"][field] = {"reported_yes":1,"reported_no":1,"not_available":1}
                answer = q.search(self.db, {"field":field,"value_state":"reported_no"})
                self.assertEqual(answer["status"],"source_observations")
                self.assertEqual(answer["total"],1)
                self.assertEqual(answer["rows"][0]["value_state"],"reported_no")
                self.assertEqual(answer["indicator_kind"],kind)
                self.assertIn("does not establish that the service is absent",answer["interpretation_limit"])

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
