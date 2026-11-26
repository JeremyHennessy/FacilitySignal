"""Reconcile the durable 19-source raw-profile index against exact release evidence."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
def read(p):
    return json.loads((ROOT/p).read_text(encoding="utf-8"))
class NationalDataUnderstandingIndexTests(unittest.TestCase):
    def test_complete_pinned_source_and_column_evidence(self):
        index=read("research/national_data_understanding_index_20261126.json")
        lock=read("research/snapshot_release_20261125.json")
        pins={s["key"]:s for s in lock["sources"]}
        self.assertEqual(set(pins),{s["source"] for s in index["sources"]})
        self.assertEqual(len(index["sources"]),19)
        rows=cols=excluded=cells=restricted=blank=0
        for s in index["sources"]:
            pin=pins[s["source"]]
            self.assertEqual((s["sha256"],s["input_rows"],s["profiled_rows"],s["excluded_rows"]),
                             (pin["sha256"],pin["input_rows"],pin["stored_rows"],pin["excluded_rows"]))
            p=read(s["profile_evidence"]["path"])
            raw=next((v for v in p.get("sources",[p]) if v["source"]==s["source"]),None)
            self.assertIsNotNone(raw)
            self.assertEqual(raw["source_sha256"],s["sha256"])
            self.assertEqual(len(s["fields"]),s["columns"])
            self.assertEqual([(f["ordinal"],f["field"]) for f in s["fields"]],
                             [(f["ordinal"],f["field"]) for f in raw["fields"]])
            for f,r in zip(s["fields"],raw["fields"]):
                counts=r.get("states",r.get("presence"))
                self.assertEqual(sum(counts.values()),s["profiled_rows"])
                self.assertEqual(f["blank"],counts.get("blank",0))
                self.assertEqual(f["all_blank"],f["blank"]==s["profiled_rows"])
                blank+=int(f["all_blank"])
                restricted+=int("presence" in r)
                self.assertEqual(f["application_approval"],"not_granted_by_this_audit")
            rows+=s["profiled_rows"];excluded+=s["excluded_rows"]
            cols+=s["columns"];cells+=s["profiled_rows"]*s["columns"]
        self.assertEqual((rows,cols,excluded,cells,restricted,blank),
                         (1904060,1433,326781,125518335,31,299))
        self.assertEqual(index["totals"]["profiled_rows"],rows)
        self.assertEqual(index["totals"]["columns"],cols)
        self.assertEqual(index["totals"]["cells_checked"],cells)
    def test_definition_metadata_not_overpromoted(self):
        index=read("research/national_data_understanding_index_20261126.json")
        sources={s["source"]:s for s in index["sources"]}
        for k,n in (("qies",473),("clia",103)):
            self.assertEqual(sources[k]["columns"],n)
            self.assertTrue(all(f["semantic_status"]=="historical_2023_publisher_candidate_only"
                                for f in sources[k]["fields"]))
        blocked=[f for f in sources["iqies"]["fields"] if f["semantic_status"].startswith("blocked")]
        self.assertEqual(len(blocked),5)
        self.assertEqual({f["field"] for f in blocked},
            {"chow_sw","ot_cntrctr_sw","ot_arngmt_sw","physn_arngmt_sw","fed_fundd_fqhc_sw"})
if __name__=="__main__": unittest.main()
