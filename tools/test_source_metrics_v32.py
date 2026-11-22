"""Synthetic tests for source measurement and priority rules."""
import unittest
from source_metrics_v32 import summarize
from source_priority_v32 import rank_sources

def row(i, source="KEIRIN.JP", success=True, complete=True, comparison="match", elapsed=100):
    return dict(attemptId=str(i),source=source,category="identity",url="https://example.invalid/test",observedAt="2026-11-22T12:00:00+09:00",target="synthetic",success=success,complete=complete,comparison=comparison,elapsedMs=elapsed)

class MetricsTests(unittest.TestCase):
    def test_count_denominators(self):
        r=summarize([row(1),row(2,success=False,complete=False,comparison="not_checked",elapsed=None)])[0]
        self.assertEqual((r["attempts"],r["successes"],r["complete"],r["compared"],r["matches"],r["timed"]),(2,1,1,1,1,1))
    def test_duplicate(self):
        with self.assertRaises(ValueError): summarize([row(1),row(1)])
    def test_invalid_comparison(self):
        with self.assertRaises(ValueError): summarize([row(1,success=False,complete=False)])
    def test_unknown_time(self):
        self.assertIsNone(summarize([row(1,elapsed=None)])[0]["medianMs"])
    def test_sparse_default(self):
        self.assertEqual(rank_sources([row(1,"WINTICKET")],"identity")[:2],["KEIRIN.JP","WINTICKET"])
    def test_prefer_quality(self):
        a=[row(i,"KEIRIN.JP",comparison="conflict",elapsed=10) for i in range(10)]
        b=[row(i+10,"WINTICKET",elapsed=1000) for i in range(10)]
        self.assertEqual(rank_sources(a+b,"identity")[0],"WINTICKET")
