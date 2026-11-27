import unittest
from scripts import weekly_azure_refresh as w
class WeeklyRefreshTests(unittest.TestCase):
    def test_release_policy(self):
        old={"release":"2026-10-28","download_url":"https://data.cms.gov/provider-data/a.csv","input_rows":100}
        meta={"released":old["release"],"url":old["download_url"]}
        self.assertEqual(w.release_state(meta,100,old),"unchanged")
        self.assertEqual(w.release_state(meta,101,old),"same_date_revision_review")
        self.assertEqual(w.release_state({**meta,"released":"2026-11-25"},110,old),"new_release")
        self.assertEqual(w.release_state({**meta,"released":"2026-11-25"},10,old),"count_change_review")
        self.assertEqual(w.release_state({**meta,"released":"2026-10-01"},100,old),"older_release_review")
    def test_private_namespace(self):
        self.assertEqual(w.safe_name(w.PREFIX+"/care-compare/hospital/"+"a"*64+"/candidate.sqlite3"),w.PREFIX+"/care-compare/hospital/"+"a"*64+"/candidate.sqlite3")
        for s in (w.archive.POINTER,w.PREFIX+"/care-compare/hospital/"+"a"*64+"/raw.csv","TowerSignal/x",w.PREFIX+"/nppes-weekly/"+"a"*64+"/../complete.json"):
            with self.assertRaises(ValueError):w.safe_name(s)
    def test_weekly_release_discovery(self):
        html='<a href="/nppes/w.zip">NPPES Data Dissemination V.2 - Weekly Update - 111626_112226</a><a href="/nppes/m.zip">NPPES Data Dissemination V.2 (November 09, 2026)</a>'
        weeks,monthly=w.discover_nppes(html)
        self.assertEqual(weeks[0]["end"],"2026-11-22")
        self.assertEqual(monthly["url"],"https://download.cms.gov/nppes/m.zip")
        with self.assertRaises(ValueError):w.discover_nppes(html.replace("/nppes/w.zip","https://example.org/w.zip"))
    def test_fingerprint_is_order_independent(self):
        self.assertEqual(w.fingerprint({"a":1,"b":2}),w.fingerprint({"b":2,"a":1}))

    def test_refresh_new_release_has_distinct_private_identity(self):
        week={"label":"synthetic","url":"https://download.cms.gov/nppes/example.zip"}
        self.assertNotEqual(w.fingerprint({"policy":w.POLICY_VERSION,"release":week}),w.fingerprint({"policy":w.POLICY_VERSION,"release":week,"private_projection":1}))

    def test_observer_final_flush_without_prior_count(self):
        import csv,io,sqlite3,tempfile,zipfile
        from pathlib import Path
        from scripts import qualify_nppes_v2 as n,archive_hcris_nppes as p
        npi=next("123456789"+str(i) for i in range(10) if n.npi_valid("123456789"+str(i)))
        h=n.REQUIRED+["Healthcare Provider Taxonomy Code_"+str(i) for i in range(2,16)]
        def csv_bytes(rows):
            f=io.StringIO();writer=csv.writer(f);writer.writerows(rows);return f.getvalue()
        def row(entity):
            d={"Entity Type Code":entity,"NPI":npi,"Provider Organization Name (Legal Business Name)":"SECRET","Provider Enumeration Date":"01/01/2024","Healthcare Provider Taxonomy Code_1":"123456789X"}
            return [d.get(k,"") for k in h]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/"source.zip"
            suffix="11162026-11222026"
            with zipfile.ZipFile(path,"w") as z:
                z.writestr("npidata_pfile_"+suffix+".csv",csv_bytes([h,row("1"),row("2")]))
                z.writestr("npidata_pfile_"+suffix+"_fileheader.csv",csv_bytes([h]))
                z.writestr("othername_pfile_"+suffix+".csv",csv_bytes([["NPI"],[npi]]))
                z.writestr("pl_pfile_"+suffix+".csv",csv_bytes([["NPI"],[npi]]))
                z.writestr("endpoint_pfile_"+suffix+".csv","SECRET ENDPOINT")
            db=root/"projection.sqlite3";a=p.nppes_project(path,db,"weekly")
            self.assertEqual(a["organization_observations"],1)
            self.assertEqual(a["taxonomy_observations"],1)
            self.assertEqual(a["individual_identifiers_retained"],0)
            with sqlite3.connect(db) as conn:self.assertNotIn("SECRET",str(list(conn.iterdump())))


    def test_weekly_store_cannot_write_even_when_called_directly(self):
        # No credential or network construction is needed to test the guard.
        store=object.__new__(w.WeeklyAzure)
        for name in (w.PREFIX+"/care-compare/hospital/"+"a"*64+"/candidate.sqlite3",
                     w.source_archive.PREFIX+"/nppes-weekly/v1/"+"a"*64+"/files/projection.sqlite3"):
            with self.assertRaisesRegex(ValueError,"Verified storage cost"):
                store.create(name,None,1,"application/octet-stream")

    def test_changed_sources_detected_without_download_or_write(self):
        from pathlib import Path
        from unittest.mock import Mock,patch
        from contextlib import ExitStack
        old={"release":"2026-10-28","download_url":"https://data.cms.gov/provider-data/a.csv","input_rows":100}
        meta={"released":"2026-11-25","url":"https://data.cms.gov/provider-data/b.csv"}
        week={"label":"new week","url":"https://download.cms.gov/nppes/w.zip","start":"2026-11-16","end":"2026-11-22"}
        monthly={"label":"new month","url":"https://download.cms.gov/nppes/m.zip"}
        ledger={"nppes_v2_qualified_baselines":{}}
        store=Mock()
        national={"pointer":{"release":"pinned"}}
        with ExitStack() as ctx:
            ctx.enter_context(patch.object(w,"load_evidence",return_value=({"sources":[]},ledger,{"hospital":old},{})))
            ctx.enter_context(patch.object(w.cms,"metadata",return_value=meta))
            ctx.enter_context(patch.object(w.cms,"count",return_value=110))
            ctx.enter_context(patch.object(w,"existing",return_value=None))
            response=ctx.enter_context(patch.object(w.nppes,"response"))
            response.return_value.__enter__.return_value.read.return_value=b"index"
            ctx.enter_context(patch.object(w,"discover_nppes",return_value=([week],monthly)))
            ctx.enter_context(patch.object(w.registry,"get_json",return_value={}))
            ctx.enter_context(patch.object(w,"discover_registry",return_value={}))
            ctx.enter_context(patch("scripts.weekly_archive_monitor.monitor",return_value={}))
            ctx.enter_context(patch.object(w,"unchanged"))
            cms=ctx.enter_context(patch.object(w,"qualify_cms_candidate"))
            nppes=ctx.enter_context(patch.object(w,"qualify_nppes_week"))
            publish=ctx.enter_context(patch.object(w,"publish_candidate"))
            result=w.run(store,national,Path("."))
            cms.assert_not_called()
            nppes.assert_not_called()
            publish.assert_not_called()
        store.create.assert_not_called()
        self.assertEqual(result["failed_checks"],[])
        self.assertFalse(result["new_candidate_writes_enabled"])
        self.assertEqual(result["sources"]["hospital"]["state"],w.WRITE_BLOCK_STATE)
        self.assertEqual(result["sources"]["nppes"]["weeks"][0]["state"],w.WRITE_BLOCK_STATE)
        self.assertEqual(result["sources"]["nppes"]["monthly"]["state"],"new_monthly_release_review")

    def test_preview_treats_storage_gate_as_review_not_unchanged(self):
        from scripts import qualify_blob_release_preview as p
        pins={k:{} for k in p.SOURCES}
        report={"format_version":1,"policy_version":w.POLICY_VERSION,"public_promotion":False,
                "failed_checks":[],"sources":{k:{"state":w.WRITE_BLOCK_STATE} for k in pins}}
        selected,blocked=p.selection(report,pins)
        self.assertEqual(selected,{})
        self.assertEqual(blocked,{k:w.WRITE_BLOCK_STATE for k in pins})
