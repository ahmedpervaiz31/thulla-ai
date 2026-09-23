"""LSTM-once-per-state must match duplicated-z forward (same weights)."""

from __future__ import annotations

import unittest

import numpy as np
import torch

from thulla_dmc.encode import ACTION_DIM, X_DIM, X_NO_ACTION_DIM, Z_DIM, Z_ROWS
from thulla_dmc.models import Model
from thulla_dmc.train import select_action, select_actions_batched


def _x_batch(n: int) -> np.ndarray:
    x = np.zeros((n, X_DIM), dtype=np.float32)
    for i in range(n):
        x[i, X_NO_ACTION_DIM + (i % ACTION_DIM)] = 1.0
        x[i, i % X_NO_ACTION_DIM] = 0.25
    return x


def _z(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal((Z_ROWS, Z_DIM), dtype=np.float32)


class LstmOnceParityTests(unittest.TestCase):
    def test_single_state_2d_matches_duplicated_z(self):
        torch.manual_seed(0)
        model = Model(device="cpu")
        model.eval()
        n = 7
        z = _z(1)
        x = torch.from_numpy(_x_batch(n))
        z_dup = torch.from_numpy(np.stack([z] * n, axis=0))
        z_one = torch.from_numpy(z)

        with torch.inference_mode():
            v_dup = model.forward(z_dup, x, return_value=True)["values"]
            v_one = model.forward(z_one, x, return_value=True)["values"]
        self.assertTrue(torch.allclose(v_dup, v_one, atol=1e-5, rtol=1e-5))

    def test_counts_matches_duplicated_z(self):
        torch.manual_seed(1)
        model = Model(device="cpu")
        model.eval()
        sizes = [3, 5, 2]
        zs = [_z(10 + i) for i in range(len(sizes))]
        xs = [_x_batch(n) for n in sizes]

        z_states = torch.from_numpy(np.stack(zs, axis=0))
        x_all = torch.from_numpy(np.concatenate(xs, axis=0))
        z_dup = torch.from_numpy(
            np.concatenate([np.stack([z] * n, axis=0) for z, n in zip(zs, sizes)], axis=0)
        )
        counts = torch.tensor(sizes, dtype=torch.long)

        with torch.inference_mode():
            v_dup = model.forward(z_dup, x_all, return_value=True)["values"]
            v_cnt = model.forward(
                z_states, x_all, return_value=True, counts=counts
            )["values"]
        self.assertTrue(torch.allclose(v_dup, v_cnt, atol=1e-5, rtol=1e-5))

    def test_batched_select_uses_obs_z(self):
        torch.manual_seed(2)
        model = Model(device="cpu")
        model.eval()

        def fake(labels, seed):
            n = len(labels)
            z = _z(seed)
            return {
                "legal_actions": list(labels),
                "x_batch": _x_batch(n),
                "z_batch": np.stack([z] * n, axis=0),
                "z": z,
                "x_no_action": np.zeros(X_NO_ACTION_DIM, dtype=np.float32),
                "position": 0,
            }

        obs_a = fake(["a0", "a1", "a2"], 20)
        obs_b = fake(["b0", "b1"], 21)
        single_a = select_action(model, obs_a, torch.device("cpu"), exp_epsilon=0.0)
        single_b = select_action(model, obs_b, torch.device("cpu"), exp_epsilon=0.0)
        batched = select_actions_batched(
            model, [obs_a, obs_b], torch.device("cpu"), exp_epsilon=0.0
        )
        self.assertEqual(batched, [single_a, single_b])


if __name__ == "__main__":
    unittest.main()
