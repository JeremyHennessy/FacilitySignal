from unittest import TestCase
from scripts.qualify_ihs_projects import TITLE,qualify

class ProjectsTest(TestCase):
    def scope(self,tail):
        return (TITLE+"\n"+tail).encode()
    def test_repeated_title_is_not_another_project(self):
        a="#### Café\nPhoto Date: 2025\nStatus: Completed\n#### Cafe\u0301\nPhoto Date: TBD\nStatus: Completed\n"
        r=qualify(self.scope(a))
        self.assertEqual((r["display_cards"],r["normalized_distinct_display_titles"],r["photo_year_range"]),(2,1,[2025,2025]))
        self.assertEqual(r["cards_with_tbd_photo_year"],1)
        self.assertNotIn("café",str(r).casefold())
    def test_disagreement_fails_closed(self):
        with self.assertRaises(ValueError):
            qualify(self.scope("#### Example\nStatus: Completed\n#### Example\nStatus: In construction\n"))
    def test_unsupported_or_missing_fields_fail_closed(self):
        for bad in ("#### example\nStatus: Unknown\n","#### example\n","#### example\nPhoto Date: today\nStatus: Completed\n"):
            with self.assertRaises(ValueError): qualify(self.scope(bad))
