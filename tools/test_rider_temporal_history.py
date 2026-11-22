import unittest
from rider_temporal_history import half_year,profile_candidate,review_key
class TemporalTests(unittest.TestCase):
    def test_boundary(self):
        self.assertEqual(half_year("2026-06-30"),"2026-H1")
        self.assertEqual(half_year("2026-07-01"),"2026-H2")
    def candidate(self,events,score="90.44"):
        return profile_candidate("000001","TEST","https://keirin.jp/pc/racerprofile?snum=000001","2026-08-01",events,score)
    def test_score_not_review(self):
        x=self.candidate([])
        self.assertFalse(x["displayedScore"]["isFinalReviewScore"])
        self.assertIsNone(x["displayedScore"]["reviewTerm"])
        self.assertFalse(x["publicationAllowed"])
    def test_order(self):
        x=self.candidate([{"effectiveFrom":"2026-07-01","grade":"A1"},{"effectiveFrom":"2026-01-01","grade":"S2"}])
        self.assertEqual([r["grade"] for r in x["gradeEvents"]],["S2","A1"])
    def test_conflict(self):
        with self.assertRaises(ValueError):
            self.candidate([{"effectiveFrom":"2026-07-01","grade":"A1"},{"effectiveFrom":"2026-07-01","grade":"S2"}])
    def test_future(self):
        with self.assertRaises(ValueError):
            self.candidate([{"effectiveFrom":"2027-01-01","grade":"S2"}])
    def test_metric_separation(self):
        self.assertNotEqual(review_key("000001",2026,1,"promotion_review","v1"),review_key("000001",2026,1,"registration_review","v1"))
if __name__=="__main__":unittest.main()
