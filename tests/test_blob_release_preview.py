import copy,hashlib,sqlite3,tempfile,unittest
from pathlib import Path
import facilitysignal as fs
from scripts import qualify_blob_release_preview as m

class BlobReleasePreviewTests(unittest.TestCase):
    def setup_report(self):
        pins={k:{"key":k,"family":"care-compare","release":"2026-10-01","sha256":"a"*64,"input_rows":100,"stored_rows":100,"download_url":"https://data.cms.gov/old.csv"} for k in m.SOURCES}
        report={"format_version":1,"policy_version":1,"public_promotion":False,"failed_checks":[],"sources":{k:{"state":"unchanged","published_baseline_release":"2026-10-01","api_count":100,"publisher":{"released":"2026-10-01","url":"https://data.cms.gov/old.csv"}} for k in m.SOURCES}}
        return pins,report
    def test_selection_and_review(self):
        pins,r=self.setup_report()
        self.assertEqual(m.selection(r,pins),({},{}))
        k="home-health";meta={"released":"2026-11-01","url":"https://data.cms.gov/new.csv"}
        r["sources"][k].update(state="private_candidate_qualified",publisher=meta,api_count=101,candidate={"publisher":meta,"api_count":101,"source_bytes":1000,"source_sha256":"b"*64,"import":{"status":"imported","dataset":k,"sha256":"b"*64,"input_rows":101,"stored_rows":101,"duplicate_rows":0}})
        selected,blocked=m.selection(r,pins)
        self.assertEqual(set(selected),{k});self.assertEqual(blocked,{})
        self.assertIn("home_health_service_evidence",m.dependency_review(selected))
        bad=copy.deepcopy(r);bad["sources"][k]["candidate"]["import"]["stored_rows"]=99
        with self.assertRaises(ValueError):m.selection(bad,pins)
        r["sources"]["dialysis"]["state"]="same_date_revision_review"
        self.assertEqual(m.selection(r,pins)[1],{"dialysis":"same_date_revision_review"})
    def test_read_only_boundary(self):
        store=m.ReadOnlyWeeklyAzure.__new__(m.ReadOnlyWeeklyAzure)
        with self.assertRaises(ValueError):store.create("x",None,0,"x")
        with self.assertRaises(ValueError):store.delete_probe("x","x")
    def test_changed_nursing_rejoins_both_citation_shards(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);base=root/"base.sqlite3";new=root/"new.sqlite3"
            fs.init(base);fs.init(new)
            pins={}
            def add(conn,key,rid,day,digest,name):
                states=fs.STATES if key=="hospital" else ["NY"]
                n=len(states)
                conn.execute("INSERT INTO releases VALUES(?,?,?,?,?,?,?,?,?)",(rid,key,day,"test",digest,n,n,0,"https://data.cms.gov/test.csv"))
                conn.execute("INSERT INTO current_release VALUES(?,?)",(key,rid))
                if key in fs.FINDING_DATASETS:
                    conn.execute("INSERT INTO findings(dataset,row_hash,ccn,provider_name,state,survey_date,survey_type,tag,category,description,severity,correction_status,correction_date,release_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(key,"a"*64,"000001","OLD CITATION NAME","NY","2026-10-01","","X","","","","","",rid))
                else:
                    for i,state in enumerate(states,1):
                        conn.execute("INSERT INTO facilities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(key,f"{i:06}",name,"Address","City",state,"00000","","","","","","",rid))
                return {"key":key,"family":"care-compare","release":day,"sha256":digest,"input_rows":n,"stored_rows":n}
            with sqlite3.connect(base) as db:
                for i,key in enumerate(sorted(m.SOURCES),1):pins[key]=add(db,key,i,"2026-10-01","a"*64,"OLD NAME")
            with sqlite3.connect(new) as db:pins["nursing"]=add(db,"nursing",1,"2026-11-01","b"*64,"NEW NAME")
            approved=root/"approved/web/public-directory";approved.mkdir(parents=True)
            lt=approved/"long-term-hospital.json";m.write_json(lt,{"records":[{"ccn":"000001","name":"OLD NAME","address":"Address","city":"City","state":"NY","zip":"00000","capacity":"17"}]})
            m.write_json(approved/"manifest.json",{"limitations":[],"field_enrichments":{"long-term-hospital":{"projection_sha256":m.sha(lt)}}})
            core=root/"core.sqlite3";m.assemble(base,{"nursing":new},pins,core)
            out=root/"preview";r=m.project(core,pins,root/"approved",out,{"nursing"},"2026-11-01")
            self.assertEqual(len(r["packs"]),11);self.assertEqual(r["provider_rows"],62);self.assertEqual(r["citation_source_rows"],2)
            for key in ("nursing-health","nursing-fire"):
                row=m.read_json(out/"web/public-directory"/(key+".json"))["records"][0]
                self.assertEqual(row["name"],"NEW NAME");self.assertEqual(row["citation_rows"],1)
            self.assertEqual(m.read_json(out/"web/public-directory/long-term-hospital.json")["records"][0]["capacity"],"17")
            self.assertFalse((out/"web/public-intelligence.json").exists())
            self.assertFalse((out/"web/hha-service-evidence.json").exists())
            self.assertIn("nursing_citation_name_join",m.dependency_review({"nursing"}))
    def test_changed_ltch_drops_stale_enrichment(self):
        self.assertIn("long_term_hospital_capacity_enrichment",m.dependency_review({"long-term-hospital"}))

    def test_candidate_receipt_and_exact_payload_readback(self):
        class MemoryStore:
            def __init__(self,files):self.files=files
            def head(self,name):
                return {"bytes":len(self.files[name]),"etag":hashlib.sha256(self.files[name]).hexdigest()}
            def chunks(self,name,etag):
                if self.head(name)["etag"]!=etag:raise ValueError("ETag drift")
                yield self.files[name]
            def list(self,prefix):
                for name in sorted(self.files):
                    if name.startswith(prefix+"/"):yield {"name":name,**self.head(name),"folder":False}
        key="hospital";ident="b"*64;prefix=m.weekly.PREFIX+"/care-compare/"+key+"/"+ident
        db_bytes=b"synthetic candidate database bytes";digest=hashlib.sha256(db_bytes).hexdigest()
        result={"candidate_database_bytes":len(db_bytes),"candidate_database_sha256":digest}
        audit=m.archive.encode(result)
        rec={"status":"COMPLETE","domain":"FACILITYSIGNAL_WEEKLY_CANDIDATE","policy_version":m.weekly.POLICY_VERSION,"key":key,"identity":ident,"public_promotion":False,"base_release":"bootstrap-1-1","base_receipt_sha256":"c"*64,"result":result,"files":[m.archive.bytes_record("audit.json",audit),m.archive.bytes_record("candidate.sqlite3",db_bytes)]}
        files={prefix+"/complete.json":m.archive.encode(rec),prefix+"/audit.json":audit,prefix+"/candidate.sqlite3":db_bytes}
        national={"pointer":{"release":"bootstrap-1-1"},"receipt_sha256":"c"*64};item={"identity":ident,"result":result}
        with tempfile.TemporaryDirectory() as d:
            p=m.read_candidate(MemoryStore(files),national,key,item,Path(d))
            self.assertEqual(p.read_bytes(),db_bytes)
        with tempfile.TemporaryDirectory() as d:
            tampered={**files,prefix+"/candidate.sqlite3":b"X"+db_bytes[1:]}
            with self.assertRaises(ValueError):m.read_candidate(MemoryStore(tampered),national,key,item,Path(d))
        with tempfile.TemporaryDirectory() as d:
            tampered={**files,prefix+"/unexpected.json":b"{}"}
            with self.assertRaises(ValueError):m.read_candidate(MemoryStore(tampered),national,key,item,Path(d))
        with tempfile.TemporaryDirectory() as d:
            wrong_base={**national,"receipt_sha256":"d"*64}
            with self.assertRaises(ValueError):m.read_candidate(MemoryStore(files),wrong_base,key,item,Path(d))
