import csv
import io
import unittest
from scripts.qualify_cms_hai_benchmark import FIELDS, benchmark, from_csv, summarize

NATIONAL=[dict(zip(FIELDS,(f"HAI_{i}_SIR","Fixture","1","","01/01/2025","12/31/2025"))) for i in range(1,7)]

class Benchmarks(unittest.TestCase):
    def test_csv_and_complete_domain(self):
        out=io.StringIO()
        writer=csv.DictWriter(out,fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(NATIONAL)
        raw=out.getvalue().encode()
        self.assertEqual(from_csv(raw),benchmark(NATIONAL))
        for altered in (raw.replace(b"Measure ID",b"Identifier"),raw+b"extra,row\n",
                        raw.replace(b"12/31/2025",b"12/31/2027"),raw.replace(b",1,,",b",0.99,,")):
            with self.subTest(altered=altered),self.assertRaises(ValueError):
                from_csv(altered)

    def test_provider_abstention_and_label_preservation(self):
        row={**NATIONAL[0],"Score":"0.2","Compared to National":"No Different than National Benchmark"}
        result=summarize([row,{**row,"Score":"Not Available","Footnote":"13"},
                          {**row,"Measure ID":"HAI_1_NUMERATOR"},
                          {**row,"Start Date":"02/01/2025"}],benchmark(NATIONAL))
        self.assertEqual(result["row_dispositions"],{"numeric_sir_exact_benchmark_context":1,
                         "source_score_unavailable":1,"unavailable_with_footnote":1,
                         "other_metric_not_used_for_benchmark":1,"no_exact_period_benchmark":1})
        self.assertEqual(result["publisher_labels_on_numeric_members"],{"No Different than National Benchmark":1})
        self.assertEqual(result["physical_site_attributions"],0)

if __name__=="__main__":
    unittest.main()
