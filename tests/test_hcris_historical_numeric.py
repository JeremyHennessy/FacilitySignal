import copy,json,unittest
from scripts import archive_hcris_historical_numeric as m
class HistoricalNumericTests(unittest.TestCase):
    def test_plan_complete_and_excludes_2024(self):
        plan=json.loads(m.PLAN.read_text())
        for form,item in plan["forms"].items():
            prior={"annual_partitions":{y:{"child_tables":{"numeric":{"rows":n}}} for y,n in item["source_year_counts"].items()}}
            prior["annual_partitions"]["2024"]={"child_tables":{"numeric":{"rows":1}}}
            self.assertEqual(m.validate_plan(form,plan,prior),item)
            bad=copy.deepcopy(plan);bad["forms"][form]["groups"].pop()
            with self.assertRaises(ValueError):m.validate_plan(form,bad,prior)
            bad=copy.deepcopy(plan);bad["forms"][form]["groups"].append(bad["forms"][form]["groups"][0])
            with self.assertRaises(ValueError):m.validate_plan(form,bad,prior)
    def test_source_counts_are_exact(self):
        plan=json.loads(m.PLAN.read_text());self.assertEqual(plan["source_numeric_rows"],sum(sum(x["source_year_counts"].values()) for x in plan["forms"].values()))
