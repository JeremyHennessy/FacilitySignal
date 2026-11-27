import unittest
from scripts.qualify_cms_hai_state_context import complete_state_context,provider_state_verdict,summarize

def row(i,kind,value):
    return {"State":"AA","Measure ID":f"HAI_{i}_{kind}","Score":value,
            "Start Date":"01/01/2025","End Date":"12/31/2025","Release":"2026-11-12"}

ROWS=[row(i,k,v) for i in range(1,7) for k,v in (("CILOWER","0.2"),("SIR","0.8"),("CIUPPER","1.4"))]

class StateContext(unittest.TestCase):
    def test_one_complete_scope_and_interval(self):
        c=complete_state_context(ROWS,"2026-11-12")
        self.assertEqual(len(c),6)
        for alternative in (ROWS[:-1], ROWS[:-1]+ROWS[:1],
                            ROWS[:-1]+[{**ROWS[-1],"State":"BB"}],
                            ROWS[:-1]+[{**ROWS[-1],"Start Date":"03/01/2025"}],
                            ROWS[:-1]+[{**ROWS[-1],"Score":"0.1"}]):
            with self.subTest(alternative=alternative), self.assertRaises(ValueError):
                complete_state_context(alternative,"2026-11-12")

    def test_context_only_and_holdouts(self):
        c=complete_state_context(ROWS,"2026-11-12")
        target=ROWS[1]
        self.assertEqual(provider_state_verdict(target,c),"same_jurisdiction_context_only")
        self.assertEqual(provider_state_verdict({**target,"State":"BB"},c),"different_jurisdiction")
        self.assertEqual(provider_state_verdict({**target,"Start Date":"02/01/2025"},c),"different_release_or_period")
        self.assertEqual(provider_state_verdict({**target,"Score":"Not Available"},c),"provider_score_unavailable")
        self.assertEqual(provider_state_verdict(ROWS[0],c),"not_sir")
        with self.assertRaises(ValueError):
            complete_state_context(ROWS,"2026-09-01")
        result=summarize(ROWS,[target],"2026-11-12")
        self.assertEqual(result["numeric_recomparisons_or_label_changes"],0)

if __name__=="__main__":
    unittest.main()
