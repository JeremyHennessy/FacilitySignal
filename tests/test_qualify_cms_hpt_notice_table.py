import json
import unittest
from scripts.qualify_cms_hpt_notice_table import qualify

HTML_TEXT = """L1: Date Action Taken | Hospital Name | Effective Date
L2: --- | --- | ---
L3: 【11†2026-04-01 (PDF)】 | Fictional Alpha Under Review * | 2026-04-01
L4: 【12†2026-05-01 (PDF)】【13†2026-06-01 (PDF)】 | Fictional Beta | 2025-01-01
L5:
L6: other
"""

class NoticeTable(unittest.TestCase):
    def test_document_count_distinct_from_rows(self):
        result=qualify(HTML_TEXT.encode())
        self.assertEqual((result["portal_rows"],result["rendered_notice_links"]),(2,3))
        self.assertEqual(result["review_label_row_counts"],{"under_review_label":1,"no_under_review_label":1})
        self.assertEqual(result["date_order_per_link"],{"effective_eq_notice":1,"effective_before_notice":2})
        self.assertNotIn("Fictional",json.dumps(result))
        self.assertEqual(result["provider_identity_links"],0)

    def test_truncation_duplicate_and_calendar_drift_fail_closed(self):
        for broken in (HTML_TEXT.replace("L4:","L8:"),HTML_TEXT.replace("【12†","【11†"),
                       HTML_TEXT.replace("2026-04-01","2026-04-31"),HTML_TEXT.split("L5:")[0],
                       HTML_TEXT.replace("Hospital Name","Facility"),
                       HTML_TEXT.replace("(PDF)","(Word)")):
            with self.subTest(broken=broken),self.assertRaises(ValueError):
                qualify(broken.encode())

if __name__=="__main__":
    unittest.main()
