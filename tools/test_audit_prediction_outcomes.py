import unittest

from audit_prediction_outcomes import audit_outcome


class PredictionOutcomeTest(unittest.TestCase):
    def test_full_order_requires_matching_pre_start_record(self):
        key = "2026-11-27|83|8"
        prior = {"予想ID": "fixture", "レースID": key, "車立て": "7",
                 "使用データ時点(JST)": "2026-11-27 22:50 JST",
                 "予想記録日時(JST)": "2026-11-27 22:50:50 JST",
                 "三連単候補": "1-2-4, 1-2-3"}
        result = {"race_id": key, "start_at": "2026-11-27 23:00 JST",
                  "confirmed": True, "order": [1, 2, 4, 5, 3, 7, 6]}
        self.assertTrue(audit_outcome(prior, result)["exact_order"])
        altered = dict(result, order=[1, 3, 2, 6, 5, 7, 4])
        self.assertFalse(audit_outcome(prior, altered)["exact_order"])
        self.assertTrue(audit_outcome(prior, altered)["winning_car_listed"])
        self.assertEqual(audit_outcome(prior, dict(result, order=[1, 2, 4]))["state"],
                         "HOLD_INCOMPLETE_ORDER")
        self.assertEqual(audit_outcome(prior, dict(result, start_at=prior["予想記録日時(JST)"]))["state"],
                         "HOLD_POST_START")
