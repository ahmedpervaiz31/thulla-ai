"""Fixed eval seed bank: same deals across repeated evaluate_model calls."""

from __future__ import annotations

import unittest

from thulla_dmc.evaluate import eval_game_seeds, evaluate_model
from thulla_dmc.models import Model


class FixedEvalSeedTests(unittest.TestCase):
    def test_seed_bank_is_contiguous(self):
        r = eval_game_seeds(3, opponent="random", eval_seed=10_000)
        h = eval_game_seeds(3, opponent="heuristic", eval_seed=10_000)
        self.assertEqual(r, [10_000, 10_001, 10_002])
        self.assertEqual(h, r)  # same deals; opponents diverge in-play

    def test_evaluate_model_is_deterministic(self):
        model = Model(device="cpu")
        model.eval()
        a = evaluate_model(model, num_games=2, opponent="random", eval_seed=42)
        b = evaluate_model(model, num_games=2, opponent="random", eval_seed=42)
        self.assertEqual(a["places"], b["places"])
        self.assertEqual(a["mean_reward"], b["mean_reward"])
        self.assertEqual(a["eval_seed"], 42)


if __name__ == "__main__":
    unittest.main()
