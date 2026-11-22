import unittest
from copy import deepcopy
from quality_v2_race import classify_race
def obs(url="https://keirin.jp/example"):
    return {"url":url,"observedAt":"2026-11-22T12:00:00+09:00","method":"direct","evidence":"SYNTHETIC TEST ONLY","raceKey":["2026-10-01","83",1],"grade":"A3","fieldSize":2,"rows":[{"car":1,"name":"TEST A","finish":"1","status":"正常"},{"car":2,"name":"TEST B","finish":"2","status":"正常"}]}
class RaceTests(unittest.TestCase):
    def test_two(self):
        a=obs(); b=obs("https://www.chariloto.com/example")
        self.assertEqual(classify_race([a,b])["grade"],"A")
        self.assertFalse(classify_race([a,b])["publicationAllowed"])
    def test_same_site(self):
        self.assertEqual(classify_race([obs(),obs("https://www.keirin.jp/example")])["grade"],"B")
    def test_conflict(self):
        a=obs(); b=obs("https://keirin.kdreams.jp/example"); b["rows"][0]["status"]="故"
        self.assertEqual(classify_race([a,b])["grade"],"C")
    def test_missing(self):
        a=obs(); a["rows"].pop()
        self.assertEqual(classify_race([a])["grade"],"D")
    def test_optional(self):
        a=obs(); b=obs("https://www.chariloto.com/example"); b["rows"][0]["time"]="12.0"
        self.assertEqual(classify_race([a,b])["grade"],"A")
