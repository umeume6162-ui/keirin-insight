import unittest
from audit_dual_intake import audit_streams
from audit_evidence_sheet import HEADERS
from test_audit_evidence_sheet import row

class DualIntakeTests(unittest.TestCase):
    def test_cross_stream_duplicate(self):
        report=audit_streams([HEADERS,row("AUTO-1","AUTO")],[HEADERS,row("MANUAL-1")])
        self.assertEqual(report["counts"],{"QUARANTINED":2})
        self.assertFalse(report["publicationAllowed"])
    def test_wrong_stream(self):
        r=audit_streams([HEADERS,row()],[HEADERS])
        self.assertIn("WRONG_INTAKE_STREAM",r["records"][0]["issues"])
    def test_cached_pending(self):
        a=row();a[14]="PENDING";a[3]="cached_official_profile"
        r=audit_streams([HEADERS],[HEADERS,[],a])
        self.assertEqual(r["counts"],{"HELD":1})
        self.assertEqual(r["records"][0]["sourceRow"],3)
        self.assertEqual(r["records"][0]["stream"],"MANUAL")
    def test_empty(self):
        r=audit_streams([HEADERS],[HEADERS])
        self.assertEqual(r["counts"],{})
        self.assertFalse(r["publicationAllowed"])
    def test_header_failure(self):
        with self.assertRaises(ValueError):audit_streams([HEADERS],[["wrong"]])
    def test_pending_cross_stream_collision(self):
        a=row();a[14]="PENDING";a[3]="cached_official_profile"
        r=audit_streams([HEADERS,row("AUTO-1","AUTO")],[HEADERS,a])
        self.assertEqual(r["counts"],{"QUARANTINED":2})
if __name__=="__main__":unittest.main()
