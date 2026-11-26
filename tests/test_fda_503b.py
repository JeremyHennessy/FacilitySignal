import unittest
from scripts.qualify_fda_503b import HEAD,audit
class FDA503BTests(unittest.TestCase):
    def test_registration_projection_and_contact_exclusion(self):
        header="<tr>"+"".join("<th>"+v+"</th>" for v in HEAD)+"</tr>"
        def row(name,initial,latest):
            return "<tr>"+"".join("<td>"+v+"</td>" for v in (name,"SECRET CONTACT",initial,latest,"Not yet inspected","N/A","N/A","N/A","Yes"))+"</tr>"
        html="<p>Updated as of 11/24/2026</p><table>"+header+row("Example A","1/2/2024","10/3/2026")+row("Example B","1/1/2026","10/1/2026")+row("Example C","1/1/2026","1/1/2025")+"</table>"
        a=audit(html.encode())
        self.assertEqual((a["input_rows"],a["stored_rows"],a["rejected_rows"]),(3,2,1))
        self.assertEqual(a["registration_year_counts"],{"initial_registration_year_2024":1,"initial_registration_year_2026":1})
        self.assertNotIn("SECRET",str(a));self.assertNotIn("Example A",str(a))
