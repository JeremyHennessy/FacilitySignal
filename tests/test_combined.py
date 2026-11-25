import json
import shutil
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
import facilitysignal as fs
import build_combined as bc

class CombinedTests(unittest.TestCase):
    def test_base_rejects_missing_source_and_changed_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            db=folder/"facilitysignal.sqlite3"
            fs.init(db)
            manifest={"db_sha256":bc.sha(db),"sources":[]}
            (folder/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"nine releases"):
                bc.validate_base(folder)
            with closing(fs.connect(db)) as conn,conn:
                conn.execute("INSERT INTO releases VALUES(1,'hospital','2026-01-01','now','hash',1,1,0,'url')")
            with self.assertRaisesRegex(ValueError,"hash mismatch"):
                bc.validate_base(folder)

    def test_full_fixture_combination_and_nonmutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            base=root/"base";base.mkdir()
            combined=root/"combined";combined.mkdir()
            db=base/"facilitysignal.sqlite3"
            fs.init(db)
            sources=[]
            with closing(fs.connect(db)) as c,c:
                for i,k in enumerate(sorted(fs.CATALOG),1):
                    c.execute("INSERT INTO releases VALUES(?,?,?,?,?,?,?,?,?)",(i,k,"2026-01-01","now","fixture-"+k,1,1,0,"url"))
                    c.execute("INSERT INTO current_release VALUES(?,?)",(k,i))
                    if k in fs.FACILITY_DATASETS:
                        c.execute("INSERT INTO facilities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(k,"010001","Fixture","1 Test","City","AL","01001","","type","","","","",i))
                    else:
                        c.execute("INSERT INTO findings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(k,"row-"+k,"010001","Fixture","AL","2026-01-01","","tag","","description","","","",i))
                    sources.append({"dataset":k,"sha256":"fixture-"+k,"expected_rows":1})
            original=bc.sha(db)
            (base/"manifest.json").write_text(json.dumps({"db_sha256":original,"sources":sources,"facility_records":7,"finding_records":2}))
            target=combined/"facilitysignal.sqlite3"
            shutil.copyfile(db,target)
            raw=combined/"raw";raw.mkdir()
            registry_sources=[]
            with closing(fs.connect(target)) as c,c:
                for k in sorted(bc.REGISTRIES):
                    p=raw/(k+".csv");p.write_text("fixture "+k)
                    h=bc.sha(p)
                    c.execute("INSERT INTO certification_releases VALUES(?,?,?,?,?,?,?,?,?)",(k,"fixture","period","api","url",h,1,"now","{}"))
                    c.execute("INSERT INTO certification_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(k,1,h,"010001","Fixture","1 Test","City","AL","01001","","","","",""))
                    registry_sources.append({"registry":k,"rows":1,"sha256":h,"source":{"zipped":False}})
            manifest={"sources":registry_sources,"certification_records":3,"db_sha256":bc.sha(target)}
            (combined/"registry-manifest.json").write_text(json.dumps(manifest))
            audit=bc.verify(base,combined)
            self.assertEqual(audit["combined_source_records"],12)
            self.assertEqual(audit["registry_rows"],{"qies":1,"iqies":1,"clia":1})
            self.assertEqual(len(audit["identifier_overlap_audit"]),2)
            self.assertTrue(all(x["same_state_candidates"]==1 for x in audit["identifier_overlap_audit"]))
            self.assertEqual(bc.sha(db),original)
            # A same-count mutation cannot pass full row reconciliation.
            with closing(fs.connect(target)) as c,c:
                c.execute("UPDATE facilities SET name='Changed' WHERE dataset='hospital'")
            manifest["db_sha256"]=bc.sha(target)
            (combined/"registry-manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"baseline rows changed"):
                bc.verify(base,combined)
