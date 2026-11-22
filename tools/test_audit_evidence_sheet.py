import unittest
from audit_evidence_sheet import audit, HEADERS, POLICY

def row(key="MANUAL-TEST",mode="MANUAL"):
    return [key,mode,"2026-11-22T09:00:00+09:00","direct_official_profile","TEST","TEST","99","TEST","TEST","99","000001","https://keirin.jp/pc/racerprofile?snum=000001","SYNTHETIC TEST ONLY","","MATCH_CANDIDATE",POLICY,"PENDING","","NOT REAL EVIDENCE"]

class EvidenceAuditTests(unittest.TestCase):
    def check(self,*rows):
        return audit([HEADERS,*rows])
    def test_valid_structure_only(self):
        r=self.check(row())
        self.assertEqual(r["counts"],{"PENDING_INDEPENDENT_REVIEW":1})
        self.assertFalse(r["publicationAllowed"])
    def test_concurrent_duplicate(self):
        r=self.check(row(),row("AUTO-TEST","AUTO"))
        self.assertEqual(r["counts"],{"QUARANTINED":2})
    def test_duplicate_record(self):
        r=self.check(row(),row())
        self.assertTrue(all("DUPLICATE_RECORD_ID" in x["issues"] for x in r["records"]))
    def test_numeric_id(self):
        x=row();x[10]=1
        self.assertEqual(self.check(x)["counts"],{"QUARANTINED":1})
    def test_wrong_profile(self):
        x=row();x[11]="https://keirin.jp/pc/racerprofile?snum=000002"
        self.assertIn("INVALID_PROFILE",self.check(x)["records"][0]["issues"])
    def test_identity_mismatch(self):
        x=row();x[8]="OTHER"
        self.assertIn("IDENTITY_MISMATCH",self.check(x)["records"][0]["issues"])
    def test_missing_evidence(self):
        x=row();x[12]=""
        self.assertIn("MISSING_EVIDENCE",self.check(x)["records"][0]["issues"])
    def test_self_approval(self):
        x=row();x[16]="APPROVED"
        self.assertIn("UNSUPPORTED_APPROVAL",self.check(x)["records"][0]["issues"])
    def test_rejected_held(self):
        x=row();x[14]="REJECTED"
        self.assertEqual(self.check(x)["counts"],{"HELD":1})
    def test_header(self):
        with self.assertRaises(ValueError):audit([["wrong"]])
if __name__=="__main__":unittest.main()
