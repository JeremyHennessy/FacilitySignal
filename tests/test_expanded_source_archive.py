import hashlib,json,os,tempfile,unittest
from pathlib import Path
from scripts.verify_expanded_source_archive import load_lock,verify_files,ROOT,validate_item
class ExpandedSourceArchiveTests(unittest.TestCase):
    def test_lock_matches_qualified_evidence(self):
        l=load_lock();ledger=json.loads((ROOT/"research/coverage_status.json").read_text())
        entries={}
        for key in ("fda_mqsa_qualified_baseline","cms_penalties_qualified_baseline","hrsa_sites_screening_baseline","hospital_cost_qualified_baseline","snf_cost_qualified_baseline"):
            sid={"fda_mqsa_qualified_baseline":"FS-011","cms_penalties_qualified_baseline":"FS-036","hrsa_sites_screening_baseline":"FS-009","hospital_cost_qualified_baseline":"FS-056","snf_cost_qualified_baseline":"FS-057"}[key]
            entries[sid]=ledger[key]
        for group in ("qcor_provider_qualified_baselines","qcor_expansion_qualified_baselines","nursing_survey_qualified_baselines"):
            for b in ledger[group].values():entries[b["audit"]["source_id"]]=b
        self.assertEqual(set(entries),{x["source_id"] for x in l["expanded_sources"]})
        for x in l["expanded_sources"]:
            b=entries[x["source_id"]];a=b["audit"];s=a.get("publisher") or a.get("source") or a
            self.assertEqual((x["url"],x["sha256"],x["bytes"]),(s["url"],a.get("source_sha256") or s["sha256"],a.get("bytes") or s["bytes"]))
            self.assertEqual(x["qualification_run"],b["run"]);self.assertEqual(x["qualification_commit"],b["commit"])
            self.assertEqual(x["qualified_rows"],a.get("privacy_screened_rows",a.get("stored_rows")))
            self.assertEqual(x["input_rows"],a["input_rows"]);self.assertEqual(x["retained_row_level_records"],0)
            self.assertFalse(b["included_in_integrated_national_baseline"])
            self.assertEqual(x["reuse_review"],"pending")
        self.assertEqual(l["ephemeral_projection_records"],865809)
        self.assertEqual(l["aggregate_screened_records"],16657)
        self.assertEqual(l["original_source_records"]+l["ephemeral_projection_records"]+l["aggregate_screened_records"],2786526)
    def test_local_byte_verification(self):
        content=b"synthetic";sha=hashlib.sha256(content).hexdigest()
        x={"source_id":"FS-999","file":"fs-999-test.csv","bytes":len(content),"sha256":sha,"url":"https://data.cms.gov/test.csv"}
        validate_item(x);l={"expanded_sources":[x]}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);os.chmod(root,0o700);p=root/x["file"]
            self.assertEqual(verify_files(l,root)["verified_files"],0)
            p.write_bytes(content);self.assertEqual(verify_files(l,root)["verified_files"],1)
            p.write_bytes(b"different");self.assertEqual(verify_files(l,root)["verified_files"],0)
            p.unlink();p.symlink_to(root/"absent");self.assertEqual(verify_files(l,root)["file_results"][0]["status"],"symlink_rejected")
        with self.assertRaises(ValueError):validate_item({**x,"file":"../unsafe.csv"})
