"""Synthetic identity collision regression tests."""
import unittest
from identity_collision import collisions

class CollisionTests(unittest.TestCase):
    def test_same_name_different_id(self):
        r=collisions([["架空選手","東京","100","000001"],["架空選手","大阪","101","000002"]])
        self.assertEqual(len(r["sameName"]),1)
        self.assertFalse(r["autoMergeAllowed"])
    def test_normalized_duplicate(self):
        r=collisions([["架空 選手","東京都","100期","000001"],["架空選手","東京","100","000001"]])
        self.assertEqual(r["sameName"],[])
        self.assertEqual(r["registrationConflicts"],[])
    def test_registration_conflict(self):
        r=collisions([["架空選手","東京","100","000001"],["別選手","大阪","101","000001"]])
        self.assertEqual(len(r["registrationConflicts"]),1)
    def test_invalid_number(self):
        with self.assertRaises(ValueError):
            collisions([["架空選手","東京","100",1]])
