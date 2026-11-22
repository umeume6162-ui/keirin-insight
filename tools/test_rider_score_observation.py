import unittest
from rider_score_observation import score_observation

class ScoreObservationTests(unittest.TestCase):
    def sample(self, **changes):
        args=dict(registration="000001",evidence_id="TEST",source="https://keirin.jp/pc/racerprofile?snum=000001",metric="profile_current_term",raw_value="70.00",source_updated_at="2026-08-01T02:36:00+09:00",retrieved_at="2026-11-22T12:00:00+09:00",acquisition_method="cached_official_profile")
        args.update(changes)
        return score_observation(**args)
    def test_distinct_metrics(self):
        a=self.sample()
        b=self.sample(metric="rolling_four_months")
        self.assertNotEqual(a["metric"],b["metric"])
        self.assertNotEqual(a["sha256"],b["sha256"])
    def test_missing_not_zero(self):
        self.assertIsNone(self.sample(raw_value="-")["value"])
        self.assertEqual(self.sample(raw_value="0.00")["value"],"0.00")
    def test_future_source(self):
        with self.assertRaises(ValueError):
            self.sample(source_updated_at="2026-12-01T02:36:00+09:00")
    def test_wrong_timezone(self):
        with self.assertRaises(ValueError):
            self.sample(retrieved_at="2026-11-22T12:00:00+00:00")
    def test_not_review_score(self):
        a=self.sample()
        self.assertIsNone(a["reviewTerm"])
        self.assertFalse(a["isFinalReviewScore"])
        self.assertFalse(a["publicationAllowed"])
        self.assertFalse(a["trainingAllowed"])
    def test_unknown_metric(self):
        with self.assertRaises(ValueError):
            self.sample(metric="registration_review")
if __name__=="__main__":unittest.main()
