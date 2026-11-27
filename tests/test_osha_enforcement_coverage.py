import hashlib,io,json,tempfile,unittest,zipfile
from contextlib import ExitStack,redirect_stdout
from unittest.mock import Mock,patch
from pathlib import Path
from scripts import archive_osha_enforcement_coverage as m
class OSHAEnforcementCoverageTests(unittest.TestCase):
    def test_source_row_and_activity_grains(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"inspection.zip";q=Path(d)/"violation.zip"
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("part1.csv","ACTIVITY_NR,NAICS_CODE,SITE_STATE,OPEN_DATE,INSP_SCOPE,ESTAB_NAME\n001,622110,NY,20250101,A,Private name\n001,622110,NY,20250101,A,Private name\n002,624120,CA,2025-02-01,D,Private name\n003,111110,CA,2025-02-01,A,Private name\n004,000000,NY,20250101,A,Private name\n")
            with zipfile.ZipFile(q,"w") as z:
                z.writestr("part1.csv","ACTIVITY_NR,CITATION_ID,DELETE_FLAG,VIOL_TYPE\n001,1,,S\n001,2,X,O\n002,1,D,W\n003,1,,S\n")
            ids,ins=m.inspect(p);v=m.violations(q,ids)
            self.assertEqual(ins["source_rows_screened"],5);self.assertEqual(ins["sector62_activity_keys"],2)
            self.assertEqual(ins["healthcare_621_623_activity_keys"],1)
            self.assertEqual(v["source_rows_screened"],4);self.assertEqual(v["matched_sector62_activity_keys"],2)
            self.assertEqual(v["matched_rows_by_delete_flag_literal"],{"blank":1,"X":1,"D":1})
            self.assertNotIn("Private name",str(ins));self.assertNotIn("001",str(v["matched_rows_by_delete_flag_literal"]))
    def test_conflicting_activity_codes_fail(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"inspection.zip"
            with zipfile.ZipFile(p,"w") as z:
                z.writestr("part1.csv","ACTIVITY_NR,NAICS_CODE,SITE_STATE,OPEN_DATE,INSP_SCOPE\n1,622110,NY,20250101,A\n1,621111,NY,20250101,A\n")
            with self.assertRaises(ValueError):m.inspect(p)

    def fixture_response(self,fail_final_head=False):
        payloads={}
        for kind,csv in {
            "inspection":"ACTIVITY_NR,NAICS_CODE,SITE_STATE,OPEN_DATE,INSP_SCOPE,ESTAB_NAME,SITE_ADDRESS\n87654321,622110,NY,20250101,A,Private name,Private address\n",
            "violation":"ACTIVITY_NR,CITATION_ID,DELETE_FLAG,VIOL_TYPE\n87654321,Restricted citation,,S\n",
        }.items():
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w") as z:z.writestr("part1.csv",csv)
            payloads[kind]=buf.getvalue()

        counts={}
        class Response(io.BytesIO):
            def __init__(self,kind,method="GET"):
                super().__init__(payloads[kind] if method=="GET" else b"")
                self.url=m.URLS[kind]
                counts[kind,method]=counts.get((kind,method),0)+1
                etag='"edition"'
                if fail_final_head and kind=="violation" and counts[kind,method]>1:etag='"changed"'
                self.headers={"Content-Length":str(len(payloads[kind])),"ETag":etag,
                              "Last-Modified":"Fri, 27 Nov 2026 11:00:59 GMT"}
            def geturl(self):return self.url
        return Response,payloads,counts

    def test_qualify_only_real_zip_pipeline_does_not_create_azure_client(self):
        response,payloads,calls=self.fixture_response()
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            receipt=Path(d)/"local.json"
            stack.enter_context(patch.dict(m.os.environ,{},clear=True))
            stack.enter_context(patch.object(m,"response",side_effect=response))
            for target,method in [(m.a,"run_key"),(m.storage,"SourceAzure"),(m.storage,"national_manifest"),
                                  (m.storage,"existing"),(m.storage,"publish"),(m,"write_aggregate")]:
                stack.enter_context(patch.object(target,method,side_effect=AssertionError(method)))
            stdout=stack.enter_context(redirect_stdout(io.StringIO()))
            m.main(["--receipt",str(receipt),"--qualify-only"])
            rec=json.loads(receipt.read_text())
            self.assertEqual(rec["status"],"QUALIFIED_LOCAL_ONLY")
            self.assertEqual(rec["azure_writes"],0)
            self.assertFalse(rec["archive_readback_verified"])
            self.assertFalse(rec["public_promotion"])
            self.assertEqual(rec["summary"]["source_rows_screened"],2)
            self.assertEqual(rec["summary"]["violation"]["matched_sector62_activity_keys"],1)
            self.assertEqual(rec["summary"]["site_or_event_rows_retained"],0)
            self.assertEqual(rec["summary"]["source_keys_retained"],0)
            self.assertEqual([p.name for p in Path(d).iterdir()],["local.json"])
            self.assertIn("OSHA_ENFORCEMENT_QUALIFIED_LOCAL_ONLY",stdout.getvalue())
            for raw in ("Private name","Private address","Restricted citation","87654321"):
                self.assertNotIn(raw,receipt.read_text()+stdout.getvalue())
            for kind,payload in payloads.items():
                self.assertEqual(rec["publisher"]["sources"][kind]["sha256"],hashlib.sha256(payload).hexdigest())
                self.assertEqual([calls[kind,"HEAD"],calls[kind,"GET"]],[2,1])

    def test_qualify_only_changed_edition_emits_no_receipt(self):
        response,_,_=self.fixture_response(fail_final_head=True)
        with tempfile.TemporaryDirectory() as d,patch.object(m,"response",side_effect=response),\
             patch.object(m.storage,"SourceAzure",side_effect=AssertionError("Azure client")):
            receipt=Path(d)/"rejected.json"
            with self.assertRaisesRegex(ValueError,"edition changed during acquisition"):
                m.main(["--qualify-only","--receipt",str(receipt)])
            self.assertFalse(receipt.exists())

    def test_default_preserves_existing_and_new_archive_semantics(self):
        for existing in (True,False):
            response,_,_=self.fixture_response()
            store=Mock()
            rec={"status":"COMPLETE","summary":{"aggregate_rows":1,"source_keys_retained":0}}
            with self.subTest(existing=existing),tempfile.TemporaryDirectory() as d,ExitStack() as stack:
                receipt=Path(d)/"archive.json"
                run_key=stack.enter_context(patch.object(m.a,"run_key"))
                client=stack.enter_context(patch.object(m.storage,"SourceAzure",return_value=store))
                national=stack.enter_context(patch.object(m.storage,"national_manifest",return_value={"national":True}))
                lookup=stack.enter_context(patch.object(m.storage,"existing",return_value=rec if existing else None))
                publish=stack.enter_context(patch.object(m.storage,"publish",return_value=rec))
                stack.enter_context(patch.object(m,"response",side_effect=response))
                stdout=stack.enter_context(redirect_stdout(io.StringIO()))
                m.main(["--receipt",str(receipt)])
                self.assertEqual(json.loads(receipt.read_text()),rec)
                run_key.assert_called_once_with(m.os.environ)
                client.assert_called_once_with(m.os.environ)
                national.assert_called_once_with(store)
                lookup.assert_called_once()
                self.assertEqual(lookup.call_args.args[:2],(store,m.KEY))
                store.close.assert_called_once()
                if existing:publish.assert_not_called()
                else:
                    publish.assert_called_once()
                    self.assertEqual(publish.call_args.args[2]["sha256"],lookup.call_args.args[2])
                    self.assertEqual(publish.call_args.args[4]["summary"]["source_rows_screened"],2)
                    self.assertEqual(publish.call_args.args[6],{"national":True})
                self.assertIn("PRIVATE_OSHA_ENFORCEMENT_COVERAGE_COMPLETE",stdout.getvalue())
