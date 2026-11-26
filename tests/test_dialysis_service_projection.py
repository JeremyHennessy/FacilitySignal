import unittest
from scripts.qualify_dialysis_service_projection import qualify,FIELDS
class DialysisProjectionTests(unittest.TestCase):
    def test_single_scope_and_address_gate(self):
        p=lambda ccn:{"ccn":ccn,"address":"1 Main St","city":"Town","state":"NY","zip":"00123"}
        public={k:p(k) for k in ("000001","000002","000003","000004","000005","000006")}
        raw=lambda k,**changes:{"prvdr_num":k,"prvdr_type_id":"7","state_cd":"NY","st_adr":"1 MAIN ST","city_name":"town","zip_cd":"00123-1234","dlys_stn_cnt":"0","hmdlys_srvc_sw":"Yes","prtnl_dlys_srvc_sw":"No","home_trng_sprt_only_srvc_sw":"Not Available",**changes}
        rows=[raw("000001"),raw("000002"),raw("000002"),raw("000003",state_cd="CA"),raw("000004",st_adr="Different"),raw("000005",prvdr_type_id="8"),raw("000006",zip_cd="")]
        records,audit=qualify(rows,public,{"7":"ESRD","8":"ASC"})
        self.assertEqual(set(records),{"000001"})
        self.assertEqual(records["000001"]["dlys_stn_cnt"],{"state":"reported_count","count":0})
        self.assertEqual(records["000001"]["prtnl_dlys_srvc_sw"],{"state":"reported_no"})
        self.assertEqual(records["000001"]["home_trng_sprt_only_srvc_sw"],{"state":"not_available"})
        self.assertEqual(set(records["000001"]),set(FIELDS))
        self.assertEqual(audit["match_dispositions"],{"corroborated":1,"multiple_esrd_identifier_candidates":1,"state_conflict_or_missing":1,"address_evidence_disagrees":1,"no_esrd_identifier_candidate":1,"incomplete_address_evidence":1})
        self.assertNotIn("Main St",str(records));self.assertNotIn("000002",str(records))
    def test_no_relabeling_unknown(self):
        public={"000001":{"address":"A","city":"B","state":"NY","zip":"00001"}}
        row={"prvdr_num":"000001","prvdr_type_id":"7","st_adr":"A","city_name":"B","state_cd":"NY","zip_cd":"00001","dlys_stn_cnt":"Not Available","hmdlys_srvc_sw":"Not Applicable","prtnl_dlys_srvc_sw":"","home_trng_sprt_only_srvc_sw":"unexpected"}
        records,_=qualify([row],public,{"7":"ESRD"})
        self.assertEqual(records["000001"]["dlys_stn_cnt"],{"state":"not_available","count":None})
        self.assertEqual(records["000001"]["hmdlys_srvc_sw"]["state"],"not_applicable_conflict")
        self.assertEqual(records["000001"]["prtnl_dlys_srvc_sw"]["state"],"blank")
        self.assertEqual(records["000001"]["home_trng_sprt_only_srvc_sw"]["state"],"unrecognized")
