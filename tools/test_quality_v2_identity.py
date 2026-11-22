"""Synthetic regression cases; never publish fixture data."""
import unittest
from quality_v2 import classify_identity

def obs(url="https://keirin.jp/example", fields=None):
    return {"url":url,"identity":fields or ["TEST A","愛知県","71期","000001"],"observedAt":"2026-11-22T12:00:00+09:00","method":"direct","evidence":"SYNTHETIC TEST ONLY"}

class IdentityV2Tests(unittest.TestCase):
    def test_two_domains(self):
        r=classify_identity([obs(),obs("https://www.chariloto.com/example",["TEST　A","愛知","71","000001"])])
        self.assertEqual(r["grade"],"A")
        self.assertFalse(r["publicationAllowed"])
        self.assertFalse(r["trainingAllowed"])
    def test_three_domains(self):
        self.assertEqual(classify_identity([obs(),obs("https://chariloto.com/example"),obs("https://keirin.kdreams.jp/example")])["grade"],"S")
    def test_same_domain(self):
        self.assertEqual(classify_identity([obs(),obs("https://www.keirin.jp/example")])["grade"],"B")
    def test_conflict(self):
        self.assertEqual(classify_identity([obs(),obs("https://chariloto.com/example",["TEST A","愛知","71","000002"])])["grade"],"C")
    def test_missing_registration(self):
        self.assertEqual(classify_identity([obs(),obs("https://chariloto.com/example",["TEST A","愛知","71",""])])["grade"],"B")
    def test_no_evidence(self):
        a=obs();a["evidence"]=""
        self.assertEqual(classify_identity([a])["grade"],"D")
    def test_unapproved_domain(self):
        self.assertEqual(classify_identity([obs("https://example.com/")])["grade"],"D")
    def test_numeric_registration(self):
        self.assertEqual(classify_identity([obs(fields=["TEST A","愛知","71",1])])["grade"],"D")
