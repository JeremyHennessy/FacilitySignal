import json,tempfile,unittest
from pathlib import Path
from scripts import build_pages_bundle_from_blob as m
class PagesBundleTests(unittest.TestCase):
    def fixture(self,root):
        stage=root/"stage";approved=root/"approved";stage.mkdir();approved.mkdir()
        for k in m.RUNTIME:
            p=approved/k;p.parent.mkdir(parents=True,exist_ok=True)
            if k=="research/snapshot_release_20261125.json":p.write_text(json.dumps({"sources":[{"key":str(i),"family":"care-compare"} for i in range(9)]}))
            elif k.startswith("research/"):p.write_text('{"sources":[]}')
            else:p.write_text(k)
            if k in m.PACKS:
                dst=stage/k;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(p.read_bytes())
        (approved/"index.html").write_text(" ".join(k+"?v="+m.sha(approved/k)[:16] for k in ("web/pages.js","web/pages.css")))
        files=[m.record(stage/k,k) for k in sorted(m.PACKS)]
        receipt={"status":"PASS","public_promotion":False,"azure_writes":0,"byte_identical_approved_packs":True,"market_rebuilt":True,"existing_enrichment_pins_preserved":True,"base_release":"test","pack_count":15,"bytes":sum(x["bytes"] for x in files),"files":files}
        r=root/"receipt.json";r.write_text(json.dumps(receipt));return stage,approved,r
    def test_minimal_exact_runtime_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);stage,approved,r=self.fixture(root)
            (approved/"private.sqlite3").write_text("must not be served")
            out=root/"out";m.build(stage,r,out,root/"manifest.json",approved)
            self.assertEqual(m.inventory(out),m.RUNTIME)
            self.assertFalse((out/"private.sqlite3").exists())
    def test_extra_or_mutated_pack_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);stage,approved,r=self.fixture(root);extra=stage/"private.sqlite3";extra.write_text("no")
            with self.assertRaises(ValueError):m.build(stage,r,root/"out",root/"manifest.json",approved)
            extra.unlink();(stage/"web/market-summary.json").write_text("mutated")
            with self.assertRaises(ValueError):m.build(stage,r,root/"out",root/"manifest.json",approved)
