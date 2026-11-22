"""Synthetic quarantine and recovery tests."""
import copy
import unittest
from test_rider_evidence import evidence, ledger
from quarantine_rider_batch import triage
from recover_rider_quarantine import recover

def entry():
    o,a=evidence()
    return {"status":"approved","observation":o,"approval":a}

class QuarantineTests(unittest.TestCase):
    def test_valid(self):
        q=triage(ledger(entry()))
        self.assertEqual(q["counts"]["candidate"],1)
        self.assertEqual(q["issues"],[])
    def test_invalid_kept(self):
        e=entry();e["approval"]["recordSha256"]="bad"
        q=triage(ledger(e))
        self.assertEqual(q["counts"]["error"],1)
        self.assertEqual(q["issues"][0]["original"],e)
        self.assertEqual(q["candidates"],[])
    def test_pending(self):
        e=entry();e["status"]="pending"
        self.assertEqual(triage(ledger(e))["counts"]["pending"],1)
    def test_rejected(self):
        e=entry();e["status"]="rejected"
        self.assertEqual(triage(ledger(e))["counts"]["rejected"],1)
    def test_all_duplicates_held(self):
        e=entry();q=triage(ledger(e,copy.deepcopy(e)))
        self.assertEqual(q["counts"]["error"],2)
        self.assertEqual(q["counts"]["candidate"],0)
    def test_malformed(self):
        q=triage(ledger(None))
        self.assertEqual(q["counts"]["error"],1)
        self.assertIsNone(q["issues"][0]["original"])

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        e=entry();e["approval"]["recordSha256"]="bad"
        self.q=triage(ledger(e))
        self.c={"index":0,"previousSha256":self.q["issues"][0]["entrySha256"],"reason":"Synthetic correction","replacement":entry()}
    def test_recovery(self):
        before=copy.deepcopy(self.q)
        r=recover(self.q,[self.c])
        self.assertEqual(self.q,before)
        self.assertEqual(r["result"]["counts"]["candidate"],1)
        self.assertEqual(r["publicationStatus"],"candidate_only")
    def test_wrong_hash(self):
        self.c["previousSha256"]="bad"
        with self.assertRaises(ValueError): recover(self.q,[self.c])
    def test_duplicate_retry(self):
        with self.assertRaises(ValueError): recover(self.q,[self.c,self.c])
    def test_no_retry(self):
        self.assertEqual(recover(self.q,[])["notRetried"],1)
    def test_pending_stays_pending(self):
        self.c["replacement"]["status"]="pending"
        self.assertEqual(recover(self.q,[self.c])["result"]["counts"]["candidate"],0)
    def test_tampered_original(self):
        self.q["issues"][0]["original"]["status"]="pending"
        with self.assertRaises(ValueError): recover(self.q,[self.c])

if __name__=="__main__":
    unittest.main()
