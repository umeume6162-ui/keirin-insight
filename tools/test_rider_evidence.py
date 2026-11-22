"""Synthetic regression tests; never production evidence."""
import copy
import unittest
from rider_evidence_intake import candidate
from rider_evidence_batch import collect
from prepare_verified_release import digest, validate
from test_verified_release import fixture

def evidence():
    source="https://keirin.jp/pc/racerprofile?snum=000001"
    facts={"name":"SYNTHETIC ONLY","prefecture":"TEST","period":"99","id":"000001"}
    obs={"observedFacts":facts,"source":source,"method":"direct_official_profile","retrievedAt":"2026-01-01T09:00:00+09:00","observer":"test-A","evidenceNote":"Synthetic fixture only"}
    record=dict(facts,source=source,verifiedDate="2026-01-01",officialVerification={"status":"verified","fields":["name","prefecture","period","id"],"source":source,"method":"direct_official_profile"})
    approval={"status":"approved","reviewer":"test-B","reviewedDate":"2026-01-01","observationSha256":digest(obs),"recordSha256":digest(record)}
    return obs,approval
def ledger(*entries):
    return {"schema":"ki-rider-evidence-ledger-v1","entries":list(entries)}
class IntakeTests(unittest.TestCase):
    def test_valid(self):
        r,e=candidate(*evidence())
        d,_=fixture();d[2]["riders"]=[r]
        validate(d,[e])
    def test_missing_approval(self):
        o,a=evidence()
        with self.assertRaises(ValueError): candidate(o,None)
    def test_self_approval(self):
        o,a=evidence();a["reviewer"]=o["observer"]
        with self.assertRaises(ValueError): candidate(o,a)
    def test_modified_observation(self):
        o,a=evidence();o["observedFacts"]["name"]="CHANGED"
        with self.assertRaises(ValueError): candidate(o,a)
    def test_record_hash(self):
        o,a=evidence();a["recordSha256"]="incorrect"
        with self.assertRaises(ValueError): candidate(o,a)
    def test_wrong_profile(self):
        o,a=evidence();o["source"]=o["source"].replace("000001","000002");a["observationSha256"]=digest(o)
        with self.assertRaises(ValueError): candidate(o,a)
    def test_cached_not_direct(self):
        o,a=evidence();o["method"]="cached_official_profile";a["observationSha256"]=digest(o)
        with self.assertRaises(ValueError): candidate(o,a)
    def test_no_timezone(self):
        o,a=evidence();o["retrievedAt"]="2026-01-01T09:00:00";a["observationSha256"]=digest(o)
        with self.assertRaises(ValueError): candidate(o,a)
    def test_empty(self):
        self.assertEqual(collect(ledger())["counts"]["approvedCandidates"],0)
    def test_pending_and_rejected(self):
        o,a=evidence();p=copy.deepcopy(o);p["observer"]="test-C"
        b=collect(ledger({"status":"pending","observation":o},{"status":"rejected","observation":p}))
        self.assertEqual(b["counts"],{"entries":2,"pending":1,"rejected":1,"approvedCandidates":0})
        self.assertEqual(b["riders"],[])
    def test_approved_batch(self):
        o,a=evidence()
        self.assertEqual(collect(ledger({"status":"approved","observation":o,"approval":a}))["counts"]["approvedCandidates"],1)
    def test_unknown_status(self):
        o,a=evidence()
        with self.assertRaises(ValueError): collect(ledger({"status":"unknown","observation":o}))
    def test_duplicate(self):
        o,a=evidence();e={"status":"pending","observation":o}
        with self.assertRaises(ValueError): collect(ledger(e,e))
    def test_duplicate_approved_identity(self):
        o,a=evidence();p=copy.deepcopy(o);p["observer"]="test-C";b=copy.deepcopy(a);b["observationSha256"]=digest(p)
        with self.assertRaises(ValueError): collect(ledger({"status":"approved","observation":o,"approval":a},{"status":"approved","observation":p,"approval":b}))
if __name__=="__main__": unittest.main()
