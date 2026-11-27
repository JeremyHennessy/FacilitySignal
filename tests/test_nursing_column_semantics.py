import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text())
class NursingColumnSemanticsTest(unittest.TestCase):
    def test_complete_exact_profile(self):
        a=read("research/nursing_column_semantics_20261127.json")
        p=next(x for x in read(a["profile_path"])["sources"] if x["source"]=="nursing")
        pin=next(x for x in read("research/snapshot_release_20261125.json")["sources"] if x["key"]=="nursing")
        self.assertEqual((a["source_sha256"],a["release"],a["rows"]),(pin["sha256"],pin["release"],14686))
        self.assertEqual(a["source_sha256"],p["source_sha256"])
        self.assertEqual(len(a["fields"]),102)
        for f,b in zip(a["fields"],p["fields"]):
            self.assertEqual((f["ordinal"],f["field"]),(b["ordinal"],b["field"]))
            self.assertEqual(f["profile_states"],b.get("states"))
            self.assertEqual(f["presence_only"],b.get("presence"))
            self.assertEqual(f["lexical_shapes"],b.get("lexical_shapes"))
            self.assertEqual(f["distinct_nonmissing"],b.get("distinct_nonmissing"))
            self.assertEqual(sum((f["profile_states"] or f["presence_only"]).values()),14686)
            self.assertFalse(f["new_application_approval"])
        self.assertEqual(a["totals"]["older_render_corroborated_fields"],99)
        self.assertEqual([f["ordinal"] for f in a["fields"] if f["rendered_printed_page"] is None],[29,75,84])
        self.assertEqual([f["ordinal"] for f in a["fields"] if f["presence_only"]],[7])
        self.assertEqual(sum(a["totals"]["dispositions"].values()),102)
        self.assertEqual(a["totals"]["new_application_approved_fields"],0)
        self.assertIsNone(a["dictionary"]["sha256"])
    def test_retained_diagnostics_are_exact(self):
        a=read("research/nursing_column_semantics_20261127.json")
        c=read(a["prior_clinical_evidence_path"])["sources"]["nursing"]
        h=next(x for x in read(a["prior_chain_evidence_path"])["audits"] if x["group"]=="chains")
        i=read(a["prior_institutional_evidence_path"])["sources"]["nursing"]
        self.assertEqual(a["source_sha256"],c["sha256"])
        self.assertEqual(a["source_sha256"],h["source_pins"]["nursing"]["sha256"])
        self.assertEqual(a["source_sha256"],i["source_sha256"])
        self.assertEqual(a["retained_clinical_cross_checks"],c["cross_checks"])
        self.assertEqual(a["retained_chain_counts"],{k:h["result"][k] for k in ("nursing","chains","cross_source_exact_ccn_state")})
        footnotes=[f for f in a["fields"] if f["prior_footnote_shape_counts"]]
        self.assertEqual(len(footnotes),15)
        self.assertEqual({f["field"] for f in footnotes},set(c["field_counts"]))
        for f in footnotes:
            self.assertEqual(f["prior_footnote_shape_counts"],c["field_counts"][f["field"]])
            self.assertEqual(sum(f["prior_footnote_shape_counts"].values()),14686)
        for n,k in ((27,"special_focus"),(30,"health_survey_over_two_years"),(31,"ownership_change_12_months"),(33,"sprinklers")):
            self.assertEqual(a["fields"][n-1]["prior_institutional_domain_counts"],i["fields"][k])
        self.assertEqual(a["fields"][100]["profile_states"],{"blank":13878,"other_nonblank":808})
        self.assertEqual(a["fields"][74]["profile_states"],{"blank":14557,"other_nonblank":129})
        self.assertEqual(a["fields"][83]["profile_states"],{"blank":14682,"other_nonblank":4})
        self.assertEqual(a["totals"]["new_domain_qualified_fields"],0)
