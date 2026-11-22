"""Synthetic regression tests; no real race observations."""
import unittest
from finish_integrity import validate_finishes

class FinishIntegrityTests(unittest.TestCase):
    def test_normal(self):
        self.assertTrue(validate_finishes(["1","2","3","4","5","6"],6))
    def test_dead_heat(self):
        self.assertTrue(validate_finishes(["1","2","3","4","5","5","7"],7))
    def test_bad_dead_heat(self):
        with self.assertRaises(ValueError):
            validate_finishes(["1","2","3","4","5","5","6"],7)
    def test_nonfinish(self):
        self.assertTrue(validate_finishes(["1","2","3","4","5","失格","棄権"],7))
    def test_wrong_size(self):
        with self.assertRaises(ValueError):
            validate_finishes(["1","2","3"],4)
    def test_gap(self):
        with self.assertRaises(ValueError):
            validate_finishes(["1","3","4","棄権"],4)
    def test_rank_outside_field(self):
        with self.assertRaises(ValueError):
            validate_finishes(["1","2","9"],3)
