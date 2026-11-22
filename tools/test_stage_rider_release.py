"""Synthetic staging integration tests; never production approval."""
import copy
import unittest
from stage_rider_release import merge
from test_rider_evidence import evidence, ledger
from test_verified_release import fixture
from prepare_verified_release import digest, validate

def baseline():
    d,_=fixture()
    d[2]["riders"]=[]
    d[2]["summary"]["rows"]=0
    return d,[]

def entry():
    o,a=evidence()
    return {"status":"approved","observation":o,"approval":a}

class StagingTests(unittest.TestCase):
    def test_add_and_preserve_previous(self):
        d,r=baseline()
        before=copy.deepcopy(d)
        p,rv,ch,counts=merge(d,r,ledger(entry()),"2026-01-02")
        self.assertEqual(d,before)
        self.assertEqual(r,[])
        self.assertEqual(counts["added"],1)
        self.assertEqual(len(ch),1)
        self.assertEqual(ch[0]["action"],"add")
        self.assertEqual(p[2]["summary"]["rows"],1)
        validate(p,rv)
    def test_pending_excluded(self):
        d,r=baseline()
        e=entry();e["status"]="pending";e.pop("approval")
        p,rv,ch,counts=merge(d,r,ledger(e),"2026-01-02")
        self.assertEqual(p[2]["riders"],[])
        self.assertEqual(rv,[])
        self.assertEqual(ch,[])
        self.assertEqual(counts["pending"],1)
    def test_rejected_excluded(self):
        d,r=baseline()
        e=entry();e["status"]="rejected"
        p,rv,ch,counts=merge(d,r,ledger(e),"2026-01-02")
        self.assertEqual(counts["rejected"],1)
        self.assertEqual(p[2]["riders"],[])
    def test_idempotent(self):
        d,r=baseline()
        e=entry()
        p,rv,_,_=merge(d,r,ledger(e),"2026-01-02")
        p2,rv2,ch,counts=merge(p,rv,ledger(e),"2026-01-02")
        self.assertEqual(p2,p)
        self.assertEqual(rv2,rv)
        self.assertEqual(ch,[])
        self.assertEqual(counts["added"],0)
    def test_existing_identity_conflict(self):
        d,r=fixture()
        with self.assertRaises(ValueError):
            merge(d,r,ledger(entry()),"2026-01-02")
    def test_invalid_prior_review(self):
        d,_=fixture()
        with self.assertRaises(ValueError):
            merge(d,[],ledger(),"2026-01-02")
    def test_future_observation(self):
        d,r=baseline()
        with self.assertRaises(ValueError):
            merge(d,r,ledger(entry()),"2025-12-31")
    def test_invalid_snapshot(self):
        d,r=baseline()
        with self.assertRaises(ValueError):
            merge(d,r,ledger(),"2026-02-30")
    def test_unapproved_claim(self):
        d,r=baseline()
        e=entry()
        e["approval"]["recordSha256"]="bad"
        with self.assertRaises(ValueError):
            merge(d,r,ledger(e),"2026-01-02")

if __name__=="__main__":
    unittest.main()
