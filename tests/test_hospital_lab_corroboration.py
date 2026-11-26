import unittest
from hospital_lab_corroboration import address_status,audit,Q_FIELDS
class Tests(unittest.TestCase):
    def test_address(self):
        a=("NY","1 MAIN ST","NYC","10001")
        self.assertEqual(address_status(a,a),"same_state_street_city_zip_agree")
        self.assertEqual(address_status(a,("NJ",*a[1:])),"state_conflict")
        self.assertEqual(address_status(a,("NY","2 MAIN ST",*a[2:])),"same_state_city_zip_agree_street_differs")
        self.assertEqual(address_status(a,("NY","","NYC","10001")),"same_state_incomplete_address")
    def test_reference_dedup(self):
        base={"STATE_CD":"NY","ST_ADR":"1 Main St","CITY_NAME":"NYC","ZIP_CD":"10001"}
        q={**base,"PRVDR_CTGRY_CD":"01","PRVDR_NUM":"123456","PGM_TRMNTN_CD":"00",**dict.fromkeys(Q_FIELDS,"")}
        q[Q_FIELDS[0]]=q[Q_FIELDS[1]]="LAB1"
        c={**base,"PRVDR_NUM":"LAB1","CLIA_TRMNTN_CD":"00","CRTFCT_TYPE_CD":"2","GNRL_FAC_TYPE_CD":"14","MLT_SITE_EXCPTN_SW":"N"}
        r=audit([q],[c],{"123456":[{"state":"NY"}]})
        b="code00_same_state_public_candidate"
        self.assertEqual(r["pairs_by_address_evidence"][b],{"same_state_street_city_zip_agree":1})
        self.assertEqual(r["reference_dispositions"][b+"|unique_candidate"],1)
