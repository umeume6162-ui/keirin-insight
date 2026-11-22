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
    e={"kind":"rider","key":"000001","status":"approved","recordSha256":digest(rider),"source":source,"reviewedDate":"2026-01-01","reviewer":"SYNTHETIC TEST","observedFacts":{"testOnly":True}}
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
    def test_summary_mismatch(self):
        d,e=fixture(); d[2]["summary"]["rows"]=2
        with self.assertRaises(ValueError): validate(d,e)

if __name__=="__main__": unittest.main()
