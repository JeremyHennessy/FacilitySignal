import sqlite3,tempfile,unittest,json
from pathlib import Path
from scripts.archive_pecos_nppes_candidates import projection,npi_valid
class NPIIdentityCandidateTests(unittest.TestCase):
    def test_type2_membership_and_conflicts(self):
        keys=[]
        for prefix in ("123456789","123456788"):
            keys.append(next(prefix+str(i) for i in range(10) if npi_valid(prefix+str(i))))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);b=p/"base.db";r=p/"registry.db";out=p/"candidate.db"
            with sqlite3.connect(b) as c:
                c.execute("CREATE TABLE facilities(dataset,ccn,state)")
                c.execute("INSERT INTO facilities VALUES('hospital','012345','NY')")
                c.execute("CREATE TABLE pecos_enrollment_rows(source,ordinal,enrollment_id,ccn,npi,projection)")
                c.executemany("INSERT INTO pecos_enrollment_rows VALUES(?,?,?,?,?,?)",[("hospital-enrollment",1,"one","012345",keys[0],json.dumps({"STATE":"NY"})),("hospital-enrollment",2,"two","012345",keys[1],json.dumps({"STATE":"NY"})),("hospital-enrollment",3,"three","012345","bad",json.dumps({"STATE":"NY"})),("snf-enrollment",1,"four","012346",keys[0],json.dumps({"STATE":"CA"}))])
            with sqlite3.connect(r) as c:
                c.execute("CREATE TABLE organization_fields(npi TEXT PRIMARY KEY,practice_state TEXT)")
                c.execute("INSERT INTO organization_fields VALUES(?,?)",(keys[0],"NY"))
            a=projection(b,r,out,4)
            self.assertEqual(a["stored_candidate_rows"],2)
            self.assertEqual(a["by_source"]["hospital-enrollment"]["care_compare_same_state_ccn"],1)
            self.assertEqual(a["by_source"]["snf-enrollment"]["nppes_region_different"],1)
            with sqlite3.connect(out) as c:self.assertNotIn(keys[1],str(list(c.iterdump())))
