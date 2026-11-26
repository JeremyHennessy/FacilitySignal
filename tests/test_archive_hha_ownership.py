import csv,hashlib,sqlite3,tempfile,unittest
from pathlib import Path
from scripts import archive_hha_ownership as h
import collect_ownership as o
class HHAOwnershipTests(unittest.TestCase):
    def test_only_organizations(self):
        header=list(o.ORG)+["TYPE - OWNER","FIRST NAME - OWNER","ADDRESS LINE 1 - OWNER"]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/"source.csv"
            row={k:"" for k in header}
            row.update({"ENROLLMENT ID":"ABCDEFGHIJKLMNO","ASSOCIATE ID":"123","ASSOCIATE ID - OWNER":"456","ORGANIZATION NAME - OWNER":"Synthetic corporation","ROLE CODE - OWNER":"01","TYPE - OWNER":"O","FIRST NAME - OWNER":"SECRET","ADDRESS LINE 1 - OWNER":"SECRET ADDRESS"})
            with path.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=header);w.writeheader();w.writerow(row);w.writerow({**row,"TYPE - OWNER":"I","ORGANIZATION NAME - OWNER":"SECRET INDIVIDUAL"})
            meta={"period":"2026-10-01/2026-12-31","modified":"2026-10-19","api":"https://data.cms.gov/test","url":"https://data.cms.gov/test.csv","zipped":False}
            db=root/"data.sqlite3";a=h.project(path,db,meta,hashlib.sha256(path.read_bytes()).hexdigest(),2,len(header))
            self.assertEqual((a["organization_role_rows"],a["excluded_individual_rows"]),(1,1))
            with sqlite3.connect(db) as c:self.assertNotIn("SECRET",str(list(c.iterdump())))
