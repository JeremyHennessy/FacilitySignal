import json,sqlite3,unittest
from pathlib import Path
from local_research import service_search,portfolio_search
from iqies_capabilities import DDL as IQ
from qies_hospital_services import DDL as Q
from identity_status_recovery import DDL as CANDIDATES
from collect_ownership import init as init_pecos
ROOT=Path(__file__).resolve().parents[1]
class LocalResearchTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.executescript((ROOT/"schema.sql").read_text())
    def tearDown(self):self.db.close()
    def seed_services(self):
        self.db.executescript(IQ+Q+CANDIDATES)
        for reg in ("iqies","qies"):
            self.db.execute("INSERT INTO certification_releases VALUES(?,?,?,?,?,?,?,?,?)",(reg,reg,"Q3","api","url","digest-"+reg,3,"date","{}"))
        self.db.execute("INSERT INTO iqies_capability_release VALUES(1,?,?,?,?,?,?)",("digest-iqies","dictionary","Q3","url",3,"date"))
        self.db.execute("INSERT INTO qies_hospital_service_release VALUES(1,?,?,?,?,?,?)",("digest-qies","layout","Q3","url","2023-04-02",3))
        for reg,n,state,ptype in [("iqies",1,"NY","7"),("iqies",2,"NY","7"),("iqies",3,"CA","8"),("qies",1,"NY","1"),("qies",2,"CA","1"),("qies",3,"NY","1")]:
            self.db.execute("INSERT INTO certification_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(reg,n,"hash",f"{n:06}","Fixture "+str(n),"Street","Town",state,"00001",ptype,"","","",""))
        self.db.executemany("INSERT INTO iqies_capability_observations VALUES(?,?,?,?,?,?)",[
            ("iqies",1,"dlys_stn_cnt","ESRD","reported_count",0),("iqies",2,"dlys_stn_cnt","ESRD","not_available",None),("iqies",3,"oprtg_room_cnt","ASC","reported_count",2)])
        self.db.executemany("INSERT INTO qies_hospital_service_observations VALUES(?,?,?,?,?)",[("qies",1,"CT_SCAN_SRVC_CD","historical_domain_code","0"),("qies",2,"CT_SCAN_SRVC_CD","historical_domain_code","2"),("qies",3,"CT_SCAN_SRVC_CD","blank",None)])
        self.db.execute("INSERT INTO releases VALUES(1,'dialysis','2026-10-28','date','hash',1,1,0,'url')")
        self.db.execute("INSERT INTO facilities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("dialysis","000001","Fixture","Street","Town","NY","00001","","Dialysis","","","","0",1))
        self.db.execute("INSERT INTO facility_registry_candidate VALUES(?,?,?,?,?,?,?,?)",("dialysis","000001","iqies",1,"same_state",1,1,1))
    def test_unloaded_not_zero(self):
        self.assertIsNone(service_search(self.db,{})["total"])
        self.assertIsNone(portfolio_search(self.db,{})["total"])
    def test_iqies_zero_and_missing(self):
        self.seed_services();p={"field":"dlys_stn_cnt","state":"NY"}
        x=service_search(self.db,p);self.assertEqual(x["total"],2)
        self.assertEqual([r["count_value"] for r in x["rows"]],[0,None])
        self.assertEqual(service_search(self.db,{**p,"min":"0","max":"0"})["total"],1)
        self.assertEqual(service_search(self.db,{**p,"value_state":"not_available"})["total"],1)
        self.assertEqual(x["rows"][0]["provider_candidates"][0]["ccn"],"000001")
        self.assertEqual(x["rows"][1]["provider_candidates"],[])
        self.db.execute("UPDATE iqies_capability_release SET source_sha256='wrong'")
        self.assertEqual(service_search(self.db,p)["status"],"lineage_mismatch")
    def test_literal_codes_and_validation(self):
        self.seed_services()
        x=service_search(self.db,{"registry":"qies","field":"CT_SCAN_SRVC_CD","code":"0"})
        self.assertEqual(x["rows"][0]["literal_code"],"0")
        self.assertIsNone(x["rows"][0]["count_value"])
        self.assertIn("provisional",x["semantic_status"])
        for p in [{"registry":"qies","min":"0"},{"field":"dntl_srgry_sw","min":"1"},{"field":"dlys_stn_cnt","min":"5","max":"2"},{"field":"bad"},{"state":"INVALID"}]:
            with self.assertRaises(ValueError):service_search(self.db,p)
    def test_portfolio_preserves_role_grain(self):
        init_pecos(self.db)
        for source in ("hospital-owner","hospital-enrollment","snf-enrollment"):
            self.db.execute("INSERT INTO pecos_releases VALUES(?,?,?,?,?,?,?,?,?,?)",(source,"period","modified","api","url","hash",3,3,0,"utf8"))
        self.db.executemany("INSERT INTO pecos_enrollment_rows VALUES(?,?,?,?,?,?,?,?)",[
            ("hospital-enrollment",1,"enroll","123","000001","npi","A",json.dumps({"STATE":"NY"})),
            ("hospital-enrollment",2,"enroll","123","000002","npi","B",json.dumps({"STATE":"CA"})),
            ("snf-enrollment",1,"enroll","123","000001","npi","C",json.dumps({"STATE":"NY"}))])
        self.db.executemany("INSERT INTO pecos_org_role_rows VALUES(?,?,?,?,?,?,?,?,?)",[
            ("hospital-owner",1,"enroll","123","456","Company","1","Role","{}"),
            ("hospital-owner",2,"enroll","wrong","456","Company","1","Role","{}"),
            ("hospital-owner",3,"enroll","123","","Unknown","1","Role","{}")])
        x=portfolio_search(self.db,{"owner_pac_id":"456"})
        self.assertEqual(x["total"],1);self.assertEqual(x["rows"][0]["enrollment_candidate_count"],2)
        x=portfolio_search(self.db,{"state":"NY","q":"Company"})
        self.assertEqual(x["rows"][0]["enrollment_candidate_count"],1)
        self.assertEqual(portfolio_search(self.db,{"q":"%"} )["total"],0)
        with self.assertRaises(ValueError):portfolio_search(self.db,{"owner_pac_id":"' OR 1=1"})
