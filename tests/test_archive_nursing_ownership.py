import csv, io, sqlite3, tempfile, unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from scripts import archive_nursing_ownership as a
from scripts import qualify_nursing_ownership as q
from scripts import azure_source_archive as storage

def row(kind="Organization", role="5% or greater direct ownership interest", pct="25%", date="01/02/2020"):
    return ["012345","Facility","excluded","Town","NY","10001",role,kind,"Example LLC",pct,date,"excluded","2026-10-01"]

def stream(rows):
    s=io.StringIO(newline="")
    w=csv.writer(s)
    w.writerow(q.HEADER)
    w.writerows(rows)
    s.seek(0)
    return s

class PrivateNursingOwnership(unittest.TestCase):
    def test_source_boundary(self):
        self.assertTrue(storage.prefix_for(a.KEY,a.PIN).endswith("/v1/"+a.PIN))
        with self.assertRaises(ValueError):
            storage.prefix_for("unreviewed-source",a.PIN)
    def test_literal_privacy_and_role_scope(self):
        rows=[row(),row("Individual",pct="77%",date="01/01/2010"),
              row(role="OPERATIONAL/MANAGERIAL CONTROL",pct="88%",date="unknown"),
              row(pct="see private text",date="see private text")]
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("PRAGMA foreign_keys=ON")
            q.project(stream(rows),4,db)
            report=a.retain_literals(stream(rows),db,4)
            self.assertEqual(report["retained_literal_rows"],3)
            records=db.execute("SELECT * FROM source_field_literals ORDER BY source_ordinal").fetchall()
            self.assertEqual(records,[(1,"01/02/2020","slash_date_shape","25%","percent_marked_shape"),
                                      (3,None,"missing_token",None,"outside_dictionary_role_review"),
                                      (4,None,"other_text_review",None,"other_text_review")])
    def test_source_shapes_do_not_interpret(self):
        self.assertEqual(a.source_literal("02/03/2020","date"),("02/03/2020","slash_date_shape"))
        self.assertEqual(a.source_literal("2020-02-30","date"),("2020-02-30","iso_shape"))
        self.assertEqual(a.source_literal("a name","date"),(None,"other_text_review"))
        self.assertEqual(a.source_literal("N/A","percentage"),(None,"missing_token"))
    def test_existing_receipt_avoids_redownload(self):
        summary={"input_rows":a.ROWS,"stored_organization_rows":a.STORED,"dispositions":{"excluded_individual":180548,"excluded_unknown_owner_type":650,"stored_organization":a.STORED},"distinct_source_ccns":12052,"repeated_projected_tuple_rows":0,"individual_rows_retained":0,"public_rows_retained":0}
        receipt={"base_receipt_sha256":"base","summary":summary}
        with tempfile.TemporaryDirectory() as tmp, patch.object(storage,"existing",return_value=receipt), patch.object(q,"download",side_effect=AssertionError("unexpected download")):
            self.assertIs(a.archive(object(),{"receipt_sha256":"base"},Path(tmp)),receipt)

if __name__=="__main__":
    unittest.main()
