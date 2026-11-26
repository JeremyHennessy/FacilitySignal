import io,sqlite3,tempfile,unittest
from pathlib import Path
from scripts import azure_source_archive as s,archive_hcris_nppes as p,qualify_nppes_v2 as n
from tests.test_azure_verified_extension import ExtensionStore,seed
class SourceArchiveTests(unittest.TestCase):
    def test_private_scope(self):
        name=s.prefix_for("nppes-weekly","a"*64)+"/files/projection.sqlite3"
        self.assertEqual(s.safe(name),name)
        for path in (s.a.POINTER,"TowerSignal/x",name.replace("projection.sqlite3","raw.zip"),name.replace("/v1/","/../")):
            with self.assertRaises(ValueError):s.safe(path)
    def test_observer_type2_only(self):
        npi=next("123456789"+str(i) for i in range(10) if n.npi_valid("123456789"+str(i)))
        header=n.REQUIRED+["Healthcare Provider Taxonomy Code_"+str(i) for i in range(2,16)]
        def row(entity):
            d={"Entity Type Code":entity,"NPI":npi,"Provider Enumeration Date":"01/02/2024","Provider Organization Name (Legal Business Name)":"SECRET","Healthcare Provider Taxonomy Code_1":"123456789X"}
            return [d.get(x,"") for x in header]
        o=p.OrgObserver()
        with sqlite3.connect(":memory:") as db:
            a=n.main_rows(iter([row("1"),row("2"),row("")]),header,db,10,organization_observer=o)
            o.flush(db);db.commit()
            self.assertEqual(a["distinct_valid_organization_npis"],1)
            self.assertEqual(db.execute("SELECT count(*) FROM organization_fields").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT code FROM organization_taxonomy").fetchone()[0],"123456789X")
            self.assertNotIn("SECRET",str(list(db.iterdump())))
    def test_source_create_only(self):
        store=ExtensionStore();seed(store);national=s.national_manifest(store);old=store.data[s.a.POINTER]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);db=root/"projection.sqlite3";db.write_bytes(b"synthetic")
            meta={"sha256":"a"*64};audit={"projection_sha256":s.sha(db),"projection_bytes":db.stat().st_size,"summary":{"rows":1}}
            r=s.publish(store,"nppes-weekly",meta,db,audit,root,national)
            self.assertTrue(r["sha256_readback"])
            self.assertEqual(s.existing(store,"nppes-weekly","a"*64),r)
            self.assertEqual(store.data[s.a.POINTER],old)
            with self.assertRaises(ValueError):s.publish(store,"nppes-weekly",meta,db,audit,root,national)
