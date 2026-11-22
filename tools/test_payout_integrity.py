"""Synthetic payout consistency regression tests."""
import unittest
from payout_integrity import allowed_orders, matches_order

def rows(*ranks):
    return [{"car":i+1,"finish":r} for i,r in enumerate(ranks)]

class PayoutTests(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(allowed_orders(rows("1","2","3","4"),3),{(1,2,3)})
    def test_wrong_order(self):
        self.assertFalse(matches_order(rows("1","2","3"),[2,1,3]))
    def test_first_tie(self):
        self.assertEqual(allowed_orders(rows("1","1","3"),3),{(1,2,3),(2,1,3)})
    def test_third_tie(self):
        self.assertEqual(allowed_orders(rows("1","2","3","3"),3),{(1,2,3),(1,2,4)})
    def test_nonfinish(self):
        self.assertEqual(allowed_orders(rows("1","2","棄権"),3),set())
    def test_duplicate_car(self):
        with self.assertRaises(ValueError):
            allowed_orders([{"car":1,"finish":"1"},{"car":1,"finish":"2"}],2)
