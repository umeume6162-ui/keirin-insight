import unittest
from race_card_missingness import classify_count,rate,split_history

class MissingnessTests(unittest.TestCase):
    def test_real_zero(self):
        self.assertEqual(classify_count(0,10,scope_known=True,source_verified=True)["value"],0)
    def test_no_starts(self):
        x=classify_count(0,0,scope_known=True,source_verified=True)
        self.assertEqual(x["state"],"NO_ELIGIBLE_STARTS")
        self.assertIsNone(x["value"])
    def test_unknown_scope(self):
        self.assertEqual(classify_count(0,10,source_verified=True)["state"],"UNKNOWN_SCOPE")
    def test_unconfirmed(self):
        self.assertIsNone(classify_count(0,10,scope_known=True)["value"])
    def test_invalid_counts(self):
        self.assertEqual(classify_count(11,10,scope_known=True,source_verified=True)["state"],"INCONSISTENT")
    def test_missing(self):
        self.assertEqual(classify_count("-",10,scope_known=True,source_verified=True)["state"],"MISSING")
    def test_rate(self):
        self.assertEqual(rate(3,10,scope_known=True,source_verified=True)["value"],.3)
        self.assertIsNone(rate(0,0,scope_known=True,source_verified=True)["value"])
    def test_transition_and_leakage(self):
        r=[{"date":"2026-06-30","gradeAtRace":"S2","independentlyVerified":True},{"date":"2026-07-02","gradeAtRace":"A1","independentlyVerified":True},{"date":"2026-07-03","gradeAtRace":"A1","independentlyVerified":False},{"date":"2026-07-05","gradeAtRace":"A1","independentlyVerified":True}]
        x=split_history(r,"2026-07-01","A1","2026-07-05")
        self.assertEqual([len(x[k]) for k in ("beforeTransition","afterTransitionInGrade","excluded")],[1,1,2])
        self.assertFalse(x["trainingAllowed"])
if __name__=="__main__":unittest.main()
