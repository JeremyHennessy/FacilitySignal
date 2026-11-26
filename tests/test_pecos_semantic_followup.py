import unittest
from pecos_semantic_followup import chow,subgroups,SUBGROUPS
class PecosFollowupTests(unittest.TestCase):
    def test_exact_documented_variant(self):
        s=[{"CHOW TYPE CODE":"CH","CHOW TYPE TEXT":v} for v in
           ("Change of Ownership","Change of Ownership (CHOW)","other")]
        r=chow(s)
        self.assertEqual(r["counts"],{"rows":3,"documented_earlier_dictionary_variant":1,"current_dictionary":1,"unresolved_text":1})
    def test_flags_overlap_and_unknown(self):
        r={"SUBGROUP - "+f:"N" for f in SUBGROUPS}
        r.update({"SUBGROUP - GENERAL":"Y","SUBGROUP - ACUTE CARE":"Y","SUBGROUP - OTHER":"",
                  "REH CONVERSION FLAG":"Y","REH CONVERSION DATE":"11/12/2025","CAH OR HOSPITAL CCN":"123456"})
        a=subgroups([r]);self.assertEqual(a["affirmative_subgroup_count_distribution"],{"2":1})
        self.assertEqual(a["subgroup_flag_counts"]["OTHER"],{"blank":1})
        self.assertEqual(a["reh_conversion_date_states"],{"ambiguous_slash":1})
if __name__=="__main__":unittest.main()
