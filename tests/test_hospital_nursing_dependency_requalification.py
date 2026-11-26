import unittest,tempfile,sqlite3,json
from pathlib import Path
from scripts import requalify_hospital_nursing_dependencies as m
class InstitutionalDependencyTests(unittest.TestCase):
    def test_pinned_reviewed_hospital_catalog(self):
        old=m.pinned_baseline("qies_hospital_infrastructure_audit_20261126.json")
        exact,svc,fte=m.reviewed_hospital_catalog(old,{"sha256":old["source_sha256"]})
        self.assertEqual(len(svc),57);self.assertEqual(len(fte),20)
        self.assertIn("OPRTG_ROOM_CNT",exact)
        with self.assertRaises(ValueError):m.reviewed_hospital_catalog(old,{"sha256":"a"*64})
    def test_registry_version_gate(self):
        self.assertFalse(m.registry_ready({"sources":{"registry_and_ownership":{"qies":{"state":"unchanged"},"clia":{"state":"new_version_review"}}}},["qies","clia"],False))
        self.assertTrue(m.registry_ready(None,["qies","clia"],True))
    def test_normalized_citation_uses_selected_provider_identity(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"citation.sqlite3"
            with sqlite3.connect(p) as db:
                db.executescript("CREATE TABLE releases(id,sha256,published_on,stored_rows);CREATE TABLE current_release(dataset,release_id);CREATE TABLE findings(dataset,ccn,state,tag,correction_status,correction_date,survey_date,release_id);")
                db.execute("INSERT INTO releases VALUES(?,?,?,?)",(1,"a"*64,"2026-10-28",1))
                db.execute("INSERT INTO current_release VALUES('nursing-fire',1)")
                db.execute("INSERT INTO findings VALUES('nursing-fire','000001','NY','K001','Past non-compliance','','2026-01-01',1)")
            pin={"sha256":"a"*64,"release":"2026-10-28","stored_rows":1}
            s=m.normalized_citation(p,"nursing-fire",pin,{("000001","NY")})
            self.assertEqual(s["distributions"]["provider_linkage"],{"same_ccn_state_provider_record":1})
            s=m.normalized_citation(p,"nursing-fire",pin,{("000001","CA")})
            self.assertEqual(s["distributions"]["provider_linkage"],{"unresolved_provider_link":1})
            self.assertEqual(s["confirmed_opportunities"],0)
