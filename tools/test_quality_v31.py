"""Synthetic tests of purpose-specific source rules."""
import unittest
from quality_v31 import classify

def obs(url, number="000001"):
    return {"url":url,"observedAt":"2026-11-22T15:00:00+09:00","method":"search_cache","evidence":"synthetic fixture","identity":["架空選手","東京","100",number]}

class PurposeTests(unittest.TestCase):
    def test_winticket_primary(self):
        r=classify([obs("https://www.winticket.jp/test"),obs("https://keirin.netkeiba.com/test")],"identity")
        self.assertEqual(r["grade"],"A")
        self.assertFalse(r["publicationAllowed"])
    def test_same_provider(self):
        r=classify([obs("https://www.winticket.jp/test"),obs("https://winticket.jp/test")],"identity")
        self.assertEqual(r["grade"],"B")
    def test_conflict(self):
        r=classify([obs("https://keirin.jp/test"),obs("https://www.winticket.jp/test","000002")],"identity")
        self.assertEqual(r["grade"],"C")
    def test_no_primary(self):
        r=classify([obs("https://keirin.netkeiba.com/test"),obs("https://www.oddspark.com/test")],"identity")
        self.assertEqual(r["grade"],"B")
    def test_missing_evidence(self):
        a=obs("https://keirin.jp/test")
        a["evidence"]=""
        self.assertEqual(classify([a],"identity")["grade"],"D")
