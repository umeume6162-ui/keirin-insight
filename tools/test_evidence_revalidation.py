"""Synthetic tests of evidence revalidation; never certify a source."""
import unittest
from evidence_revalidation import audit

class RevalidationTests(unittest.TestCase):
    def test_missing_original(self):
        r=audit([{"recordId":"synthetic"}])[0]
        self.assertEqual(r["status"],"REVALIDATION_REQUIRED")
        self.assertIn("originalEvidenceRef",r["missing"])
        self.assertFalse(r["publicationAllowed"])
    def test_filled_fields_still_require_review(self):
        r=audit([dict(recordId="synthetic",url="https://example.invalid",observedAt="2026-11-22T12:00:00+09:00",method="direct",originalEvidenceRef="fixture")])[0]
        self.assertEqual(r["status"],"ORIGINAL_REVIEW_REQUIRED")
        self.assertFalse(r["trainingAllowed"])
    def test_whitespace(self):
        self.assertIn("recordId",audit([{"recordId":" "}])[0]["missing"])
