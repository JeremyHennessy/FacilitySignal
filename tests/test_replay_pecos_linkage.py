import sqlite3
import tempfile
from pathlib import Path
import unittest

from scripts.replay_pecos_linkage import fingerprint,replay

class ReplayTests(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.path=Path(td.name)/"synthetic.sqlite"
        with sqlite3.connect(self.path) as c:
            c.executescript("""
            CREATE TABLE facilities(dataset,ccn,state);
            INSERT INTO facilities VALUES('hospital','001234','NY'),('long-term-hospital','001234','NY'),
                ('nursing','009999','CA'),('hospital','001237','FL');
            CREATE TABLE pecos_releases(source,period);
            INSERT INTO pecos_releases VALUES('hospital-enrollment','2026-11'),('hospital-owner','2026-11-01/2026-11-30'),
                ('snf-enrollment','2026-11'),('snf-owner','2026-11');
            CREATE TABLE pecos_enrollment_rows(source,enrollment_id,pac_id,ccn,projection);
            INSERT INTO pecos_enrollment_rows VALUES
                ('hospital-enrollment','A','P','001234','{"STATE":"NY"}'),
                ('hospital-enrollment','A','P','001234','{"STATE":"NY"}'),
                ('hospital-enrollment','B','P','001234','{"STATE":"NY"}'),
                ('hospital-enrollment','B','P','001235','{"STATE":"CA"}'),
                ('hospital-enrollment','C','P','001234','{}'),
                ('hospital-enrollment','D','P','001236','{"STATE":"CA"}'),
                ('hospital-enrollment','E','P','001237','{"STATE":"CA"}'),
                ('snf-enrollment','A','P','009999','{"STATE":"CA"}');
            CREATE TABLE pecos_org_role_rows(source,enrollment_id,pac_id);
            INSERT INTO pecos_org_role_rows VALUES
                ('hospital-owner','A','P'),('hospital-owner','B','P'),('hospital-owner','C','P'),
                ('hospital-owner','D','P'),('hospital-owner','E','P'),('hospital-owner','F','P'),
                ('snf-owner','A','P');
            """)
        self.expected={"hospital":{"enrollments":7,"roles":6},"snf":{"enrollments":1,"roles":1}}

    def run_replay(self,expected=None):
        n,h=fingerprint(self.path)
        return replay(self.path,n,h,self.expected if expected is None else expected)

    def test_aggregate_dispositions_conserve_roles_and_leave_database_unchanged(self):
        before=fingerprint(self.path)
        r=self.run_replay()
        self.assertEqual(set(r["families"]["hospital"]["role_dispositions"].values()),{1})
        self.assertEqual(r["families"]["snf"]["role_dispositions"]["same_state_provider_candidate"],1)
        self.assertNotIn("001234",str(r))
        self.assertEqual(fingerprint(self.path),before)

    def test_directory_conflicting_states_abstain_even_when_one_agrees(self):
        with sqlite3.connect(self.path) as c:
            c.execute("INSERT INTO facilities VALUES('rehabilitation','001234','CA')")
        r=self.run_replay()["families"]["hospital"]["role_dispositions"]
        self.assertEqual(r["same_state_provider_candidate"],0)
        self.assertEqual(r["directory_state_conflict"],2)

    def test_wrong_digest_rejected_before_database_processing(self):
        n,_=fingerprint(self.path)
        with self.assertRaisesRegex(ValueError,"not the pinned"):
            replay(self.path,n,"0"*64,self.expected)

    def test_provider_period_mismatch_abstains_without_partial_result(self):
        with sqlite3.connect(self.path) as c:
            c.execute("UPDATE pecos_releases SET period='2026-10' WHERE source='snf-owner'")
        with self.assertRaisesRegex(ValueError,"months"):
            self.run_replay()

    def test_wrong_count_rejected(self):
        with self.assertRaisesRegex(ValueError,"counts"):
            self.run_replay({"hospital":{"enrollments":1,"roles":6},"snf":{"enrollments":1,"roles":1}})
