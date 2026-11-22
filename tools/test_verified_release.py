"""Synthetic tests only. Never generate production approval records."""
import copy
import unittest
from prepare_verified_release import validate, digest, POLICY

def fixture():
    a={"schema":"ki-public-results-index-v1","publicationPolicy":POLICY,"source_snapshot_date":"2026-01-01","latest_race_date":"","summary":{"races":0,"rider_rows":0},"races":[]}
    b={"schema":"ki-rider-results-v1","publicationPolicy":POLICY,"snapshotDate":"2026-01-01","latestEventDate":"","columns":["date","trackCode","race","number","name","prefecture","period","finishRaw","track","riderClass","sourceUrl"],"summary":{"races":0,"rows":0,"riders":0},"rows":[]}
    source="https://keirin.jp/pc/racerprofile?snum=000001"
    rider={"id":"000001","name":"TEST ONLY","prefecture":"TEST","period":"99","source":source,"verifiedDate":"2026-01-01","officialVerification":{"status":"verified","source":source,"fields":["name","prefecture","period","id"]}}
    i={"schema":"ki-official-rider-ids-v1","publicationPolicy":POLICY,"summary":{"rows":1},"riders":[rider]}
    l={"schema":"ki-line-snapshots-v1","publicationPolicy":POLICY,"summary":{"races":0,"rider_rows":0},"races":[]}
    e={"kind":"rider","key":"000001","status":"approved","recordSha256":digest(rider),"source":source,"reviewedDate":"2026-01-01","reviewer":"SYNTHETIC TEST","observedFacts":{k:rider[k] for k in ("name","prefecture","period","id")},"retrievedAt":"2026-01-01T09:00:00+09:00","evidenceNote":"Synthetic fixture only"}
    return [a,b,i,l],[e]

class ReleaseTests(unittest.TestCase):
    def test_valid_synthetic_fixture(self):
        validate(*fixture())
    def test_missing_review(self):
        d,e=fixture()
        with self.assertRaises(ValueError): validate(d,[])
    def test_pending_review(self):
        d,e=fixture(); e[0]["status"]="pending"
        with self.assertRaises(ValueError): validate(d,e)
    def test_data_changed(self):
        d,e=fixture(); d[2]["riders"][0]["name"]="ALTERED"
        with self.assertRaises(ValueError): validate(d,e)
    def test_duplicate(self):
        d,e=fixture(); d[2]["riders"].append(copy.deepcopy(d[2]["riders"][0])); d[2]["summary"]["rows"]=2
        with self.assertRaises(ValueError): validate(d,e)
    def test_nonofficial_source(self):
        d,e=fixture(); d[2]["riders"][0]["source"]="https://example.com/?snum=000001"
        with self.assertRaises(ValueError): validate(d,e)
    def test_mixed_generation(self):
        d,e=fixture(); d[1]["snapshotDate"]="2026-01-02"
        with self.assertRaises(ValueError): validate(d,e)
    def test_observed_value_mismatch(self):
        d,e=fixture(); e[0]["observedFacts"]["prefecture"]="OTHER"
        with self.assertRaises(ValueError): validate(d,e)
    def test_missing_observed_field(self):
        d,e=fixture(); del e[0]["observedFacts"]["period"]
        with self.assertRaises(ValueError): validate(d,e)
    def test_missing_timezone(self):
        d,e=fixture(); e[0]["retrievedAt"]="2026-01-01T09:00:00"
        with self.assertRaises(ValueError): validate(d,e)
    def test_review_precedes_retrieval(self):
        d,e=fixture(); e[0]["retrievedAt"]="2026-01-02T09:00:00+09:00"
        with self.assertRaises(ValueError): validate(d,e)
    def test_summary_mismatch(self):
        d,e=fixture(); d[2]["summary"]["rows"]=2
        with self.assertRaises(ValueError): validate(d,e)


class ChangeAuditTests(unittest.TestCase):
    def setUp(self):
        from release_change_audit import audit_changes
        self.audit=audit_changes
        self.old,self.reviews=fixture()
        self.new=copy.deepcopy(self.old)
        self.new[2]["riders"][0]["name"]="TEST CORRECTED"
        before=self.old[2]["riders"][0]
        after=self.new[2]["riders"][0]
        self.e={"kind":"rider","key":before["id"],"action":"correct","beforeSha256":digest(before),"afterSha256":digest(after),"source":before["source"],"reviewedDate":"2026-01-02","reason":"SYNTHETIC TEST","reviewer":"SYNTHETIC TEST"}
    def test_unchanged(self):
        self.assertEqual(self.audit(self.old,self.old,[]),[])
    def test_correct_with_evidence(self):
        changes=self.audit(self.old,self.new,[self.e])
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]["action"],"correct")
        self.assertEqual(changes[0]["before"],self.old[2]["riders"][0])
        self.assertEqual(changes[0]["after"],self.new[2]["riders"][0])
    def test_correct_without_evidence(self):
        with self.assertRaises(ValueError): self.audit(self.old,self.new,[])
    def test_wrong_hash(self):
        self.e["afterSha256"]="invalid"
        with self.assertRaises(ValueError): self.audit(self.old,self.new,[self.e])
    def test_duplicate_correction(self):
        with self.assertRaises(ValueError): self.audit(self.old,self.new,[self.e,self.e])
    def test_unused_correction(self):
        with self.assertRaises(ValueError): self.audit(self.old,self.old,[self.e])
    def test_nonofficial_correction(self):
        self.e["source"]="https://example.com/"
        with self.assertRaises(ValueError): self.audit(self.old,self.new,[self.e])
    def test_withdrawal(self):
        self.new[2]["riders"]=[]; self.new[2]["summary"]["rows"]=0
        self.e["action"]="withdraw"; self.e["afterSha256"]=None
        self.assertEqual(self.audit(self.old,self.new,[self.e])[0]["action"],"withdraw")
        with self.assertRaises(ValueError): self.audit(self.old,self.new,[])
    def test_addition(self):
        self.old[2]["riders"]=[]; self.old[2]["summary"]["rows"]=0
        self.assertEqual(self.audit(self.old,self.new,[])[0]["action"],"add")

if __name__=="__main__": unittest.main()
