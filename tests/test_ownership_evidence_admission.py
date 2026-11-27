import json
import sqlite3
import unittest

from ownership_evidence import profile


class OwnershipAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
        CREATE TABLE facilities(dataset,ccn,state);
        CREATE TABLE pecos_releases(source PRIMARY KEY,modified,period,url);
        CREATE TABLE pecos_enrollment_rows(source,ccn,enrollment_id,pac_id,projection);
        CREATE TABLE pecos_org_role_rows(source,enrollment_id,pac_id);
        INSERT INTO facilities VALUES('nursing','001234','NY');
        INSERT INTO pecos_releases VALUES('snf-enrollment','e','2026-11','e'),('snf-owner','o','2026-11-01/2026-11-30','o');
        INSERT INTO pecos_org_role_rows VALUES ('snf-owner','e','p'),('snf-owner','e2','p2');
        """)
        self.enroll("001234","NY")
        self.enroll("001234","NY","e2","p2")

    def enroll(self,ccn,state,e="e",p="p",source="snf-enrollment"):
        fields={} if state is None else {"STATE":state}
        self.db.execute("INSERT INTO pecos_enrollment_rows VALUES (?,?,?,?,?)",(source,ccn,e,p,json.dumps(fields)))

    def check(self):
        return profile(self.db,"nursing","001234")

    def period(self,value):
        self.db.execute("UPDATE pecos_releases SET period=? WHERE source='snf-owner'",(value,))

    def test_equivalent_month_and_repeated_agreeing_enrollment(self):
        self.enroll("001234"," ny ")
        value=self.check()
        self.assertEqual(value["enrollment_rows"],3)
        self.assertEqual(value["organization_role_rows"],2)
        self.assertEqual(value["held_organization_role_rows"],0)

    def test_conflicting_provider_or_state_is_held_without_multiplication(self):
        self.enroll("001235","NY")
        self.enroll("001234","CA")
        self.enroll("001234",None)
        value=self.check()
        self.assertEqual((value["organization_role_rows"],value["held_organization_role_rows"]),(1,1))
        self.assertEqual(value["organization_role_link_status"],"some_roles_held_provider_ambiguity")

    def test_another_source_family_does_not_create_conflict(self):
        self.enroll("001235","CA",source="hospital-enrollment")
        self.assertEqual(self.check()["organization_role_rows"],2)

    def test_different_valid_month_holds_all_roles_not_enrollment(self):
        self.period("2026-10")
        value=self.check()
        self.assertEqual(value["organization_role_link_status"],"held_period_mismatch")
        self.assertEqual(value["enrollment_rows"],2)
        self.assertIsNone(value["organization_role_rows"])

    def test_invalid_and_incomplete_period_remain_unknown(self):
        for bad in ("", "2026-11-01/2026-11-29", "0000-11", "2026-13", "2026-Q3"):
            self.period(bad)
            value=self.check()
            self.assertEqual(value["organization_role_link_status"],"held_period_unverified")
            self.assertIsNone(value["organization_role_rows"])


if __name__=="__main__":
    unittest.main()
