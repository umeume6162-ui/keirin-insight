import unittest

from study_line_roles import summarize


class LineRoleStudyTest(unittest.TestCase):
    def test_positions_are_paired_and_lower_dead_heat_is_retained(self):
        key = "2026-10-05|75|1"
        result = {"races": [{"key": key, "grade": "A1/A2", "size": 7, "date": "2026-10-05"}]}
        lines = {"races": [{"key": key, "forecastGroups": [[1, 2, 3], [4, 5], [6, 7]],
                            "riders": [{"number": n, "name": str(n), "prefecture": "東京", "period": "99"}
                                       for n in range(1, 8)]}]}
        ranks = [2, 1, 3, 4, 5, 5, 7]
        riders = {"rows": [[str(n), "東京", "99", "2026-10-05", "松山", "75", 1, str(rank), n]
                           for n, rank in enumerate(ranks, 1)]}
        result_summary = summarize(result, lines, riders)
        self.assertEqual(result_summary["races"], 1)
        self.assertEqual(result_summary["roles"]["2026-10"]["three_rider_second"]["wins"], 1)
        riders["rows"][2][7] = "2"
        self.assertEqual(summarize(result, lines, riders)["excluded"], {"ambiguous_top_three": 1})
        riders["rows"][2][0] = "other"
        self.assertEqual(summarize(result, lines, riders)["excluded"], {"identity_or_roster": 1})

    def test_same_meeting_comparison_keeps_only_shared_meetings(self):
        keys = ["2026-10-05|75|1", "2026-10-05|75|2", "2026-10-06|75|1"]
        result = {"races": [{"key": key, "grade": "A1/A2", "size": 7, "date": key[:10]}
                            for key in keys]}
        rows = [{"number": n, "name": str(n), "prefecture": "東京", "period": "99"}
                for n in range(1, 8)]
        formations = [[[1, 2, 3], [4, 5], [6, 7]], [[1, 2, 3], [4, 5, 6], [7]]]
        lines = {"races": [{"key": key, "forecastGroups": formations[i % 2], "riders": rows}
                           for i, key in enumerate(keys)]}
        riders = {"rows": [[str(n), "東京", "99", key[:10], "松山", "75", int(key[-1]), str(n), n]
                           for key in keys for n in range(1, 8)]}
        report = summarize(result, lines, riders, compare_same_meeting=True)
        self.assertEqual(report["matched_meetings"], 1)
        self.assertEqual(report["formations"]["3-2-2"]["races"], 1)
        self.assertEqual(report["formations"]["3-3-1"]["three_rider_lines"], 2)
