import unittest

from thulla.eval.metrics import brier_score, lose_rate_ci, reliability_bins
from thulla.eval.runner import run_calibrate_game, run_strength_game


class MetricsTests(unittest.TestCase):
    def test_perfect_brier_is_zero(self):
        pairs = [(0.0, 0), (1.0, 1), (0.0, 0), (1.0, 1)]
        self.assertEqual(brier_score(pairs), 0.0)

    def test_reliability_bins(self):
        pairs = [(0.1, 0)] * 10 + [(0.1, 1)] * 0 + [(0.75, 1)] * 8 + [(0.75, 0)] * 2
        rows = reliability_bins(pairs, bin_width=0.1)
        by_lo = {round(r["lo"], 1): r for r in rows}
        self.assertIn(0.1, by_lo)
        self.assertEqual(by_lo[0.1]["emp_freq"], 0.0)
        self.assertIn(0.7, by_lo)
        self.assertAlmostEqual(by_lo[0.7]["emp_freq"], 0.8)

    def test_lose_rate_ci_bounds(self):
        rate, lo, hi = lose_rate_ci(25, 100)
        self.assertAlmostEqual(rate, 0.25)
        self.assertLess(lo, rate)
        self.assertGreater(hi, rate)


class InstrumentedGameTests(unittest.TestCase):
    def test_calibrate_game_logs_decisions(self):
        records, loser = run_calibrate_game(seed=42, mc_samples=20)
        self.assertGreater(len(records), 0)
        self.assertIsNotNone(loser)
        self.assertTrue(all(0.0 <= p <= 1.0 and y in (0, 1) for p, y in records))

    def test_strength_game_runs(self):
        lost, seat, rank = run_strength_game(seed=7, mc_samples=20)
        self.assertIn(lost, (True, False))
        self.assertEqual(seat, 7 % 4)
        self.assertIn(rank, (1, 2, 3, 4))
        self.assertEqual(lost, rank == 4)

    def test_strength_self_play_runs(self):
        lost, seat, rank = run_strength_game(
            seed=9, mc_samples=20, opponents="self"
        )
        self.assertIn(lost, (True, False))
        self.assertEqual(seat, 9 % 4)
        self.assertIn(rank, (1, 2, 3, 4))


if __name__ == "__main__":
    unittest.main()
