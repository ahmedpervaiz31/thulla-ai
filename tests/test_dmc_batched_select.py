"""Batched actor action selection for multi-env CPU inference."""

from __future__ import annotations

import unittest

import numpy as np
import torch

from thulla_dmc.encode import ACTION_DIM, X_DIM, X_NO_ACTION_DIM, Z_DIM, Z_ROWS
from thulla_dmc.models import Model
from thulla_dmc.train import select_action, select_actions_batched


def _fake_obs(legal_labels: list[str]) -> dict:
    n = len(legal_labels)
    x_batch = np.zeros((n, X_DIM), dtype=np.float32)
    z_batch = np.zeros((n, Z_ROWS, Z_DIM), dtype=np.float32)
    for i in range(n):
        x_batch[i, X_NO_ACTION_DIM + (i % ACTION_DIM)] = 1.0
    return {
        "legal_actions": list(legal_labels),
        "x_batch": x_batch,
        "z_batch": z_batch,
        "x_no_action": np.zeros(X_NO_ACTION_DIM, dtype=np.float32),
        "z": np.zeros((Z_ROWS, Z_DIM), dtype=np.float32),
        "position": 0,
    }


class BatchedSelectTests(unittest.TestCase):
    def test_batched_matches_single_greedy(self):
        torch.manual_seed(0)
        model = Model(device="cpu")
        model.eval()
        obs_a = _fake_obs(["a0", "a1", "a2"])
        obs_b = _fake_obs(["b0", "b1"])

        single_a = select_action(model, obs_a, torch.device("cpu"), exp_epsilon=0.0)
        single_b = select_action(model, obs_b, torch.device("cpu"), exp_epsilon=0.0)
        batched = select_actions_batched(
            model, [obs_a, obs_b], torch.device("cpu"), exp_epsilon=0.0
        )
        self.assertEqual(batched, [single_a, single_b])

    def test_batched_argmax_per_env_slice(self):
        model = Model(device="cpu")
        model.eval()
        obs_a = _fake_obs(["a0", "a1", "a2"])
        obs_b = _fake_obs(["b0", "b1", "b2", "b3"])

        # Prefer last of A (idx 2), second of B (idx 1) within concatenated rows.
        forced = torch.tensor(
            [0.0, 0.1, 0.9, 0.2, 1.5, 0.3, 0.4], dtype=torch.float32
        )

        def _forward(z, x, return_value=False, exp_epsilon=0.0):
            assert return_value
            return {"values": forced.unsqueeze(-1)}

        model.forward = _forward  # type: ignore[method-assign]

        out = select_actions_batched(
            model, [obs_a, obs_b], torch.device("cpu"), exp_epsilon=0.0
        )
        self.assertEqual(out, ["a2", "b1"])


if __name__ == "__main__":
    unittest.main()
