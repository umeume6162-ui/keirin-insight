"""Regression tests for shared V4 rider intake preflight; synthetic fixtures only."""
import copy
import unittest
from audit_evidence_sheet import HEADERS, POLICY
from preflight_rider_intake import preflight

def fixture(mode="MANUAL"):
    return ["TEST-RIDER-001",mode,"2026-11-22T17:00:00+09:00",
            "cached_official_profile","試験 太郎","神奈","105",
            "試験　太郎","神奈川県","105期","012345",
            "https://keirin.jp/pc/racerprofile?snum=012345",
            "synthetic test evidence","fixture only","PENDING",POLICY,
            "PENDING","","synthetic; never write to production"]

class TestPreflight(unittest.TestCase):
    def setUp(self):
        self.original=["試験 太郎","神奈","105","012345"]
        self.auto=[HEADERS.copy()]
        self.manual=[HEADERS.copy()]
        self.row=fixture()

    def run_check(self,row=None):
        return preflight(self.original,self.row if row is None else row,self.auto,self.manual)

    def test_manual_auto_parity(self):
        for mode in ("AUTO","MANUAL"):
            with self.subTest(mode=mode):
                self.assertEqual(self.run_check(fixture(mode)),
                                 {"eligible":True,"issues":[],"publicationAllowed":False})

    def test_direct_pending(self):
        self.row[3]="direct_official_profile"
        self.assertTrue(self.run_check()["eligible"])
        self.assertEqual(self.row[14],"PENDING")

    def test_identity_mismatch(self):
        for index,value,code in ((7,"別人","NAME_MISMATCH"),
                                 (8,"大阪府","PREFECTURE_MISMATCH"),
                                 (9,"106期","PERIOD_MISMATCH"),
                                 (10,"012346","REGISTRATION_MISMATCH")):
            with self.subTest(index=index):
                row=self.row.copy()
                row[index]=value
                result=self.run_check(row)
                self.assertFalse(result["eligible"])
                self.assertIn(code,result["issues"])

    def test_leading_zero(self):
        self.row[10]="12345"
        self.assertIn("INVALID_REGISTRATION",self.run_check()["issues"])

    def test_numeric_registration(self):
        self.row[10]=12345
        self.assertIn("INVALID_CANDIDATE",self.run_check()["issues"])

    def test_cross_stream_duplicate(self):
        other=fixture("AUTO")
        other[0]="TEST-OTHER"
        self.auto.append(other)
        result=self.run_check()
        self.assertFalse(result["eligible"])
        self.assertIn("REPEATED_REGISTRATION",result["issues"])

    def test_missing_evidence(self):
        self.row[12]=""
        self.assertIn("MISSING_EVIDENCE",self.run_check()["issues"])

    def test_invalid_source(self):
        self.row[11]="https://example.com/pc/racerprofile?snum=012345"
        self.assertIn("INVALID_SOURCE",self.run_check()["issues"])

    def test_wrong_timezone(self):
        self.row[2]="2026-11-22T08:00:00+00:00"
        self.assertIn("INVALID_CACHED_JST",self.run_check()["issues"])

    def test_pending_required(self):
        self.row[16]="APPROVED"
        self.assertIn("PENDING_REQUIRED",self.run_check()["issues"])

    def test_invalid_policy(self):
        self.row[15]="OLD"
        self.assertIn("POLICY_MISMATCH",self.run_check()["issues"])

    def test_invalid_header(self):
        self.auto=[["invalid"]]
        with self.assertRaises(ValueError): self.run_check()

    def test_no_input_mutation(self):
        before=copy.deepcopy((self.original,self.row,self.auto,self.manual))
        self.run_check()
        self.assertEqual(before,(self.original,self.row,self.auto,self.manual))

if __name__=="__main__":
    unittest.main()
