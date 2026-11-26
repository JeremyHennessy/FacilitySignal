import unittest
from scripts import stage_blob_public_packs as m
class PublicStageTests(unittest.TestCase):
    def test_exact_approved_scope(self):
        self.assertEqual(len(m.PACKS),15)
        self.assertTrue(all(x.startswith("web/") and x.endswith(".json") for x in m.PACKS))
        self.assertIn("web/public-directory/manifest.json",m.PACKS)
        self.assertFalse(any("research/" in x or "sqlite" in x for x in m.PACKS))
