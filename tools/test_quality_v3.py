import unittest
from quality_v3 import classify
def obs(url):
    return {"url":url,"observedAt":"2026-11-22T12:00:00+09:00","method":"direct","evidence":"SYNTHETIC ONLY","identity":["TEST","東京","99","000001"]}
class TestV3(unittest.TestCase):
    def test_fallback(self):
        a=[obs("https://keirin.jp/test"),obs("https://keirin.netkeiba.com/test")]
        self.assertEqual(classify(a,"identity")["grade"],"B")
        self.assertEqual(classify(a,"identity",True)["grade"],"A")
    def test_aux_only(self):
        a=[obs("https://winticket.jp/test"),obs("https://sp.oddspark.com/test")]
        self.assertEqual(classify(a,"identity",True)["grade"],"B")
    def test_aliases(self):
        a=[obs("https://keirin.jp/test"),obs("https://sp.oddspark.com/test"),obs("https://www.oddspark.com/test")]
        self.assertEqual(classify(a,"identity",True)["grade"],"A")
    def test_conflict(self):
        a=[obs("https://keirin.jp/test"),obs("https://winticket.jp/test")]
        a[1]["identity"][3]="000002"
        self.assertEqual(classify(a,"identity",True)["grade"],"C")
    def test_no_publication(self):
        a=[obs("https://keirin.jp/test"),obs("https://winticket.jp/test")]
        self.assertFalse(classify(a,"identity",True)["publicationAllowed"])
